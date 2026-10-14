"""Attack workers turn a frozen AttackSpec into an Observation. They never assign verdicts."""

from typing import Protocol

from gauntlet.contracts import AttackSpec, Observation, WorkerKind

from .sandbox import EnvironmentHandle


class TestWorker(Protocol):
    @property
    def kind(self) -> WorkerKind: ...

    async def run(self, spec: AttackSpec, environment: EnvironmentHandle) -> Observation: ...
