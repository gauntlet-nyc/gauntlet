"""Read-only access to recorded history (SurrealDB core in production). Never writes."""

from collections.abc import Sequence
from typing import Protocol

from gauntlet.contracts import HistoricalDecision, LineageEdge, NodeRef


class LineageStore(Protocol):
    async def edges_from(self, node: NodeRef) -> Sequence[LineageEdge]: ...

    async def edges_to(self, node: NodeRef) -> Sequence[LineageEdge]: ...


class HistoricalEventStore(Protocol):
    async def get_decision(self, decision_id: str) -> HistoricalDecision | None: ...
