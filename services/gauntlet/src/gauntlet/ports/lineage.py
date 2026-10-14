"""Read-only access to recorded history (SurrealDB core in production). Never writes."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from gauntlet.contracts import HistoricalDecision, LineageEdge, NodeRef, ToolEvent


class LineageStore(Protocol):
    async def edges_from(self, node: NodeRef) -> Sequence[LineageEdge]: ...

    async def edges_to(self, node: NodeRef) -> Sequence[LineageEdge]: ...


class HistoricalEventStore(Protocol):
    async def get_decision(self, decision_id: str) -> HistoricalDecision | None: ...

    async def tool_events(
        self, target_id: str, tool_name: str, start_at: datetime, end_at: datetime
    ) -> Sequence[ToolEvent]:
        """Recorded operations in [start_at, end_at], ascending by time. Read-only."""
        ...
