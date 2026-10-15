"""Bounded typed UI execution through the browser port."""

import asyncio
from uuid import uuid4

from gauntlet.contracts import ActionRecord, AttackSpec, Observation, WorkerKind
from gauntlet.ports.browser import BrowserProvider
from gauntlet.ports.errors import EnvironmentUnavailableError, UnknownOracleError
from gauntlet.ports.oracle import TrustedOracleRegistry
from gauntlet.ports.sandbox import EnvironmentHandle


class UIWorker:
    def __init__(self, browser: BrowserProvider, oracles: TrustedOracleRegistry) -> None:
        self._browser = browser
        self._oracles = oracles

    @property
    def kind(self) -> WorkerKind:
        return "ui"

    async def run(self, spec: AttackSpec, environment: EnvironmentHandle) -> Observation:
        for oracle_id in spec.oracle_ids:
            if not self._oracles.is_registered(oracle_id):
                raise UnknownOracleError("plan references an unregistered oracle")
        records: list[ActionRecord] = []
        status: str = "completed"
        session: str | None = None
        if (
            spec.worker_kind != self.kind
            or spec.target_id != environment.target_id
            or spec.fixture_id != environment.fixture_id
        ):
            status = "environment_error"
        elif any(step.action in {"chat", "test_api"} for step in spec.steps):
            status = "aborted"
        else:
            try:
                async with asyncio.timeout(spec.max_runtime_seconds):
                    session = await self._browser.open_session(environment)
                    for index, step in enumerate(spec.steps):
                        if index >= spec.max_actions:
                            status = "budget_exceeded"
                            break
                        record = await self._browser.perform(session, index, step)
                        if record.step_index != index or record.action != step.action:
                            status = "environment_error"
                            break
                        records.append(record)
                        if record.outcome in {"error", "skipped"}:
                            status = "environment_error"
                            break
                        if record.outcome == "blocked" and record.action != "click":
                            status = "aborted"
                            break
            except TimeoutError:
                status = "budget_exceeded"
            except EnvironmentUnavailableError:
                status = "environment_error"
            finally:
                if session is not None:
                    try:
                        async with asyncio.timeout(min(5, spec.max_runtime_seconds)):
                            await self._browser.close_session(session)
                    except (EnvironmentUnavailableError, TimeoutError):
                        status = "environment_error"
        return Observation.model_validate(
            {
                "observation_id": f"obs-{uuid4().hex}",
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
