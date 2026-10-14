"""Recall scoping: which recorded decisions are reachable from a trigger, and how.

Breadth-first over recorded lineage edges, so each decision gets its shortest provenance path.
Only decisions inside the incident window and on the trigger's target are exposures. Edges
recorded after the window closes are ignored (no hindsight). Exposure is not harm.
"""

from collections import deque
from dataclasses import dataclass
from typing import Final

from gauntlet.contracts import (
    ExposureRecord,
    LineageEdge,
    NodeKind,
    NodeRef,
    RecallTrigger,
)
from gauntlet.contracts.lineage import MAX_EXPOSURE_HOPS
from gauntlet.ports import HistoricalEventStore, LineageStore

TRIGGER_NODE_KINDS: Final[dict[str, NodeKind]] = {
    "document": "document_chunk",
    "memory": "memory",
    "model_version": "model_version",
    "prompt_version": "prompt_version",
    "policy_version": "policy_version",
}


@dataclass(frozen=True)
class ScopeLimits:
    max_hops: int = 6
    max_nodes: int = 5000


@dataclass(frozen=True)
class ExposureScope:
    exposures: tuple[ExposureRecord, ...]
    gaps: tuple[str, ...]


class RecallScoper:
    def __init__(
        self,
        lineage: LineageStore,
        history: HistoricalEventStore,
        limits: ScopeLimits | None = None,
    ) -> None:
        self._lineage = lineage
        self._history = history
        self._limits = limits or ScopeLimits()
        if not 1 <= self._limits.max_hops <= MAX_EXPOSURE_HOPS:
            raise ValueError(f"max_hops must be between 1 and {MAX_EXPOSURE_HOPS}")

    async def trace(self, recall_id: str, trigger: RecallTrigger) -> ExposureScope:
        node_kind = TRIGGER_NODE_KINDS.get(trigger.kind)
        if node_kind is None:
            return ExposureScope(
                (), (f"trigger kind '{trigger.kind}' is scoped by event audit, not lineage",)
            )
        start = NodeRef(kind=node_kind, node_id=trigger.reference)
        exposures: list[ExposureRecord] = []
        gaps: list[str] = []
        visited: set[NodeRef] = {start}
        queue: deque[tuple[NodeRef, tuple[LineageEdge, ...]]] = deque([(start, ())])

        while queue:
            node, path = queue.popleft()
            if len(path) >= self._limits.max_hops:
                gaps.append(f"lineage beyond {self._limits.max_hops} hops was not traced")
                continue
            for edge in await self._lineage.edges_from(node):
                if edge.recorded_at > trigger.end_at or edge.target in visited:
                    continue
                if len(visited) >= self._limits.max_nodes:
                    gaps.append(f"lineage traversal stopped at {self._limits.max_nodes} nodes")
                    return ExposureScope(tuple(exposures), tuple(dict.fromkeys(gaps)))
                visited.add(edge.target)
                next_path = (*path, edge)
                if edge.target.kind == "decision":
                    exposure = await self._exposure(recall_id, trigger, start, next_path, gaps)
                    if exposure is not None:
                        exposures.append(exposure)
                queue.append((edge.target, next_path))
        return ExposureScope(tuple(exposures), tuple(dict.fromkeys(gaps)))

    async def _exposure(
        self,
        recall_id: str,
        trigger: RecallTrigger,
        start: NodeRef,
        path: tuple[LineageEdge, ...],
        gaps: list[str],
    ) -> ExposureRecord | None:
        decision_id = path[-1].target.node_id
        decision = await self._history.get_decision(decision_id)
        if decision is None:
            gaps.append(f"lineage references decision {decision_id} with no recorded decision")
            return None
        if decision.target_id != trigger.target_id:
            return None
        if not trigger.start_at <= decision.occurred_at <= trigger.end_at:
            return None
        return ExposureRecord(
            exposure_id=f"{recall_id}:{decision_id}",
            recall_id=recall_id,
            decision_id=decision_id,
            trigger_node=start,
            path=path,
            direct=len(path) == 1,
        )
