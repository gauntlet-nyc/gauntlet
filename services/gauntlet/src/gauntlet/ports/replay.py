"""Replay execution against pinned state with real-world side effects blocked."""

from dataclasses import dataclass
from typing import Protocol

from gauntlet.contracts import HistoricalDecision, ReplayResult, ReplaySpec


class ReplayEngine(Protocol):
    async def replay(self, spec: ReplaySpec) -> ReplayResult:
        """Missing critical inputs must yield 'not_replayable', never a fabricated match."""
        ...


@dataclass(frozen=True)
class ReplayWorld:
    """The pinned historical environment a decision ran in (code, image, fixture state)."""

    source_sha: str
    fixture_id: str
    fixture_checksum: str
    image_digest: str | None = None


class ReplayWorldResolver(Protocol):
    async def world_for(self, decision: HistoricalDecision) -> ReplayWorld | None:
        """None when the historical environment cannot be reconstructed."""
        ...
