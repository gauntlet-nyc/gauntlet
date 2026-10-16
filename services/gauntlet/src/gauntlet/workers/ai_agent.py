"""Bounded AI-agent attack execution through the agent channel port. Never assigns verdicts."""

import asyncio

from gauntlet.contracts import (
    ActionRecord,
    AttackSpec,
    ChatStep,
    EvidenceSubject,
    Observation,
    ToolCallRecord,
    WorkerKind,
)
from gauntlet.ports.agent import AgentChannel
from gauntlet.ports.errors import EnvironmentUnavailableError, UnknownOracleError
from gauntlet.ports.oracle import TrustedOracleRegistry
from gauntlet.ports.sandbox import EnvironmentHandle


def is_agent_subject_for(environment: EnvironmentHandle, subject: EvidenceSubject) -> bool:
    return (
        subject.environment_id == environment.environment_id
        and subject.source_sha == environment.source_sha
        and subject.fixture_checksum == environment.fixture_checksum
        and subject.collector == "api_collector"
        and subject.step_index is None
    )


class AIAgentWorker:
    def __init__(self, channel: AgentChannel, oracles: TrustedOracleRegistry) -> None:
        self._channel = channel
        self._oracles = oracles

    @property
    def kind(self) -> WorkerKind:
        return "ai_agent"

    async def run(
        self, spec: AttackSpec, environment: EnvironmentHandle, subject: EvidenceSubject
    ) -> Observation:
        for oracle_id in spec.oracle_ids:
            if not self._oracles.is_registered(oracle_id):
                raise UnknownOracleError("plan references an unregistered oracle")
        records: list[ActionRecord] = []
        calls: list[ToolCallRecord] = []
        status = "completed"
        if (
            spec.worker_kind != self.kind
            or spec.target_id != environment.target_id
            or spec.fixture_id != environment.fixture_id
            or not is_agent_subject_for(environment, subject)
        ):
            status = "environment_error"
        elif not all(isinstance(step, ChatStep) for step in spec.steps):
            status = "aborted"
        else:
            try:
                async with asyncio.timeout(spec.max_runtime_seconds):
                    for index, step in enumerate(spec.steps):
                        if index >= spec.max_actions:
                            status = "budget_exceeded"
                            break
                        assert isinstance(step, ChatStep)
                        exchange = await self._channel.converse(environment, subject, index, step)
                        if exchange.record.step_index != index or exchange.record.action != "chat":
                            status = "environment_error"
                            break
                        records.append(exchange.record)
                        calls.extend(exchange.tool_calls)
                        if exchange.record.outcome in {"error", "skipped"}:
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
                "tool_calls": tuple(calls),
                "evidence_ids": tuple(
                    dict.fromkeys(e for record in records for e in record.evidence_ids)
                ),
            }
        )
