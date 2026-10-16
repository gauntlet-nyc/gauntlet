"""One Gate attempt = run a frozen attack once in one environment, then ask the trusted oracle.

Executors return a ``GateAttempt`` built only from trusted records: the worker's observation,
the oracle's verdict and the artifact bytes read back from the write-once store.
"""

from typing import Protocol

from gauntlet.contracts import AttackSpec, EvidenceSubject, Observation, OracleVerdict
from gauntlet.contracts.evidence import EvidenceCollector
from gauntlet.ports import ArtifactStore, EnvironmentHandle, StoredArtifact

from .pair_verdict import GateAttempt


class SubjectWorker(Protocol):
    """A worker that captures evidence for a preallocated subject (UI, AI-agent, API...)."""

    async def run(
        self, spec: AttackSpec, environment: EnvironmentHandle, subject: EvidenceSubject
    ) -> Observation: ...


class EvidenceOracle(Protocol):
    """Reads stored evidence itself; never trusts the observation's own claims."""

    async def evaluate(
        self,
        oracle_id: str,
        plan: AttackSpec,
        observation: Observation,
        subject: EvidenceSubject,
    ) -> OracleVerdict: ...


class AttemptExecutor(Protocol):
    @property
    def collector(self) -> EvidenceCollector: ...

    async def attempt(
        self, attack: AttackSpec, environment: EnvironmentHandle, subject: EvidenceSubject
    ) -> GateAttempt: ...


class OracleAttemptExecutor:
    """Worker -> registered evidence oracle -> artifacts re-read from the store."""

    def __init__(
        self,
        worker: SubjectWorker,
        oracle: EvidenceOracle,
        artifacts: ArtifactStore,
        *,
        collector: EvidenceCollector = "browser_collector",
    ) -> None:
        self._worker = worker
        self._oracle = oracle
        self._artifacts = artifacts
        self._collector: EvidenceCollector = collector

    @property
    def collector(self) -> EvidenceCollector:
        return self._collector

    async def attempt(
        self, attack: AttackSpec, environment: EnvironmentHandle, subject: EvidenceSubject
    ) -> GateAttempt:
        observation = await self._worker.run(attack, environment, subject)
        verdicts = tuple(
            [
                await self._oracle.evaluate(oracle_id, attack, observation, subject)
                for oracle_id in attack.oracle_ids
            ]
        )
        stored: list[StoredArtifact] = []
        for artifact_id in observation.evidence_ids:
            item = await self._artifacts.get(artifact_id)
            if item is not None:
                stored.append(item)
        return GateAttempt(subject, observation, verdicts, tuple(stored))
