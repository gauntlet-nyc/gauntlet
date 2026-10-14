"""SurrealDB Agent Memory boundary (a separate service from SurrealDB core)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from gauntlet.contracts import MemoryLens, SurfaceKind, TemporalMemoryFact


@dataclass(frozen=True)
class MemoryQuery:
    scope: str
    lens: MemoryLens
    surface_kinds: frozenset[SurfaceKind]
    as_of: datetime
    limit: int = 20


class MemoryReader(Protocol):
    async def recall(self, query: MemoryQuery) -> Sequence[TemporalMemoryFact]:
        """Facts visible to ``query.lens`` and known at ``query.as_of``. Callers re-filter."""
        ...


class MemoryWriter(Protocol):
    async def remember(self, fact: TemporalMemoryFact) -> None:
        """Append only. A correction is a new fact with ``supersedes`` set; never overwrite."""
        ...
