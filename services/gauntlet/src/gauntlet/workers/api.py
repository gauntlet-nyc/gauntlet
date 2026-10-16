"""Bounded API attack execution through the ApiClient port. Never assigns verdicts."""

import asyncio

from gauntlet.contracts import (
    ActionRecord,
    ApiRequestStep,
    AttackSpec,
    EvidenceSubject,
    Observation,
    WorkerKind,
)
from gauntlet.ports.api import ApiClient
from gauntlet.ports.errors import EnvironmentUnavailableError, UnknownOracleError
from gauntlet.ports.oracle import TrustedOracleRegistry
from gauntlet.ports.sandbox import EnvironmentHandle

from .ai_agent import is_agent_subject_for


class ApiWorker:
    def __init__(self, client: ApiClient, oracles: TrustedOracleRegistry) -> None:
        self._client = client
        self._oracles = oracles

    @property
    def kind(self) -> WorkerKind:
        return "api"

    async def run(
        self, spec: AttackSpec, environment: EnvironmentHandle, subject: EvidenceSubject
    ) -> Observation:
        for oracle_id in spec.oracle_ids:
            if not self._oracles.is_registered(oracle_id):
                raise UnknownOracleError("plan references an unregistered oracle")
        records: list[ActionRecord] = []
        status = "completed"
        if (
            spec.worker_kind != self.kind
            or spec.target_id != environment.target_id
            or spec.fixture_id != environment.fixture_id
            or not is_agent_subject_for(environment, subject)
        ):
            status = "environment_error"
        elif not all(isinstance(step, ApiRequestStep) for step in spec.steps):
            status = "aborted"
        else:
            try:
                async with asyncio.timeout(spec.max_runtime_seconds):
                    for index, step in enumerate(spec.steps):
                        if index >= spec.max_actions:
                            status = "budget_exceeded"
                            break
                        assert isinstance(step, ApiRequestStep)
                        record = await self._client.request(environment, subject, index, step)
                        if record.step_index != index or record.action != "test_api":
                            status = "environment_error"
                            break
                        records.append(record)
                        if record.outcome in {"error", "skipped"}:
                            status = "environment_error"
                            break
            except TimeoutError:
                status = "budget_exceeded"
            except EnvironmentUnavailableError:
                status = "environment_error"
        return Observation.model_validate(
            {
                "observation_id": subject.observation_id,
                "attack_id": spec.attack_id,
                "environment_id": environment.environment_id,
                "source_sha": environment.source_sha,
                "fixture_checksum": environment.fixture_checksum,
                "status": status,
                "action_log": tuple(records),
                "evidence_ids": tuple(
                    dict.fromkeys(e for record in records for e in record.evidence_ids)
                ),
            }
        )
