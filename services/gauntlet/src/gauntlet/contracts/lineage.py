"""Historical lineage graph. Edges point in the direction of influence: source → target.

Only recorded edges establish exposure. Similarity search may *suggest* sources, but it is
never an edge and never proof (master plan Section 9.3).
"""

from typing import Final, Literal, Self

from pydantic import Field, model_validator

from .common import Identifier, Sha256Hex, ShortText, StrictDTO, UtcDatetime

NodeKind = Literal[
    "document_chunk", "memory", "decision", "tool_event",
    "model_version", "prompt_version", "policy_version",
]  # fmt: skip
Relation = Literal["retrieved_by", "wrote", "read_by", "derived_into", "configured", "produced"]

ALLOWED_EDGES: Final[frozenset[tuple[str, str, str]]] = frozenset(
    {
        ("document_chunk", "retrieved_by", "decision"),
        ("decision", "wrote", "memory"),
        ("memory", "read_by", "decision"),
        ("document_chunk", "derived_into", "memory"),
        ("model_version", "configured", "decision"),
        ("prompt_version", "configured", "decision"),
        ("policy_version", "configured", "decision"),
        ("decision", "produced", "tool_event"),
    }
)
MAX_EXPOSURE_HOPS: Final = 12


class NodeRef(StrictDTO):
    kind: NodeKind
    node_id: Identifier


class LineageEdge(StrictDTO):
    edge_id: Identifier
    source: NodeRef
    relation: Relation
    target: NodeRef
    recorded_at: UtcDatetime
    evidence_ids: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def relation_fits_kinds(self) -> Self:
        if (self.source.kind, self.relation, self.target.kind) not in ALLOWED_EDGES:
            raise ValueError(
                f"{self.source.kind} -{self.relation}-> {self.target.kind} is not a lineage edge"
            )
        return self


class ToolEvent(StrictDTO):
    """One recorded tool operation. `outcome='unknown'` is never treated as success or failure."""

    event_id: Identifier
    decision_id: Identifier | None = None
    target_id: Identifier
    tool_name: Identifier
    actor_ref: Identifier
    arguments_hash: Sha256Hex
    occurred_at: UtcDatetime
    outcome: Literal["succeeded", "failed", "unknown"]
    result_hash: Sha256Hex | None = None
    side_effect_ids: tuple[Identifier, ...] = ()


class ExposureRecord(StrictDTO):
    """A decision reachable from the trigger through recorded edges. Exposure is not harm."""

    exposure_id: Identifier
    recall_id: Identifier
    decision_id: Identifier
    trigger_node: NodeRef
    path: tuple[LineageEdge, ...] = Field(min_length=1, max_length=MAX_EXPOSURE_HOPS)
    direct: bool
    note: ShortText | None = None

    @model_validator(mode="after")
    def path_is_connected(self) -> Self:
        if self.path[0].source != self.trigger_node:
            raise ValueError("path must start at the trigger node")
        for previous, current in zip(self.path, self.path[1:], strict=False):
            if previous.target != current.source:
                raise ValueError("path edges must be connected")
        if self.path[-1].target != NodeRef(kind="decision", node_id=self.decision_id):
            raise ValueError("path must end at the exposed decision")
        if self.direct != (len(self.path) == 1):
            raise ValueError("direct exposure means exactly one edge")
        return self
