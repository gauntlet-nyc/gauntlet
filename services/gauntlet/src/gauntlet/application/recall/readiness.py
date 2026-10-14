"""Missing-data semantics for counterfactual replay (master plan Sections 3.2 and 9.4).

A decision is replayable only if every *critical* input was recorded. Inputs that lineage says
were used (retrieved KB, read memory) become critical even if the recorder forgot to flag them.
Missing never means safe: an unreplayable decision stays exposed and goes to manual review.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from gauntlet.contracts import HistoricalDecision, LineageEdge, MissingInput

_ALWAYS_CRITICAL: tuple[tuple[str, str], ...] = (
    ("tool_results_hash", "recorded tool outputs are required to replay without live calls"),
    ("input_messages_hash", "the original conversation input is required to replay"),
)


@dataclass(frozen=True)
class ReplayReadiness:
    decision_id: str
    replayable: bool
    missing: tuple[MissingInput, ...]


def assess_readiness(
    decision: HistoricalDecision, incoming_edges: Sequence[LineageEdge]
) -> ReplayReadiness:
    missing: dict[str, MissingInput] = {m.field: m for m in decision.missing_inputs}

    def require(field: str, reason: str) -> None:
        if getattr(decision, field) is None and not (field in missing and missing[field].critical):
            missing[field] = MissingInput(field=field, reason=reason, critical=True)

    for field, reason in _ALWAYS_CRITICAL:
        require(field, reason)
    relations = {edge.relation for edge in incoming_edges}
    if "retrieved_by" in relations:
        require(
            "kb_snapshot_hash", "the decision retrieved KB content but no snapshot was recorded"
        )
    if "read_by" in relations:
        require("memory_snapshot_hash", "the decision read memory but no snapshot was recorded")

    ordered = tuple(sorted(missing.values(), key=lambda m: m.field))
    return ReplayReadiness(
        decision_id=decision.decision_id,
        replayable=not any(m.critical for m in ordered),
        missing=ordered,
    )
