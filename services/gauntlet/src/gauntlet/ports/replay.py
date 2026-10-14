"""Replay execution against pinned state with real-world side effects blocked."""

from typing import Protocol

from gauntlet.contracts import ReplayResult, ReplaySpec


class ReplayEngine(Protocol):
    async def replay(self, spec: ReplaySpec) -> ReplayResult:
        """Missing critical inputs must yield 'not_replayable', never a fabricated match."""
        ...
