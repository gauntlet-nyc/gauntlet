"""A-04 / Phase 4 gate: a past decision links to a KB chunk, a memory write and a downstream
read; a deliberately missing tool result marks a decision not replayable."""

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest
from gauntlet.application.recall import RecallScoper, ScopeLimits, assess_readiness
from gauntlet.contracts import (
    ExposureRecord,
    HistoricalDecision,
    LineageEdge,
    MissingInput,
    NodeRef,
    RecallTrigger,
)
from pydantic import ValidationError

DAY = datetime(2026, 10, 5, 10, 0, tzinfo=UTC)
HASH = "ab" * 32


def node(kind: str, node_id: str) -> NodeRef:
    return NodeRef.model_validate({"kind": kind, "node_id": node_id})


def edge(
    edge_id: str, source: NodeRef, relation: str, target: NodeRef, at: datetime
) -> LineageEdge:
    return LineageEdge.model_validate(
        {"edge_id": edge_id, "source": source, "relation": relation, "target": target,
         "recorded_at": at}
    )  # fmt: skip


def decision(decision_id: str, at: datetime, **overrides: object) -> HistoricalDecision:
    fields: dict[str, object] = {
        "decision_id": decision_id,
        "target_id": "cartwheel-fixture",
        "occurred_at": at,
        "agent_id": "support-agent",
        "actor_ref": "synthetic-customer-17",
        "model_id": "example-model-id",
        "prompt_version": "support-v3",
        "policy_version": "refund-policy-7",
        "tool_results_hash": HASH,
        "kb_snapshot_hash": HASH,
        "memory_snapshot_hash": HASH,
        "input_messages_hash": HASH,
        "structured_action": "start_refund",
    }
    fields.update(overrides)
    return HistoricalDecision.model_validate(fields)


KB117 = node("document_chunk", "kb-117")
KB200 = node("document_chunk", "kb-200")
MEM083 = node("memory", "mem-083")
D001, D007, D009, D012 = (node("decision", f"decision-{n}") for n in ("001", "007", "009", "012"))

EDGES = (
    edge("e1", KB117, "retrieved_by", D001, DAY),
    edge("e2", D001, "wrote", MEM083, DAY + timedelta(seconds=1)),
    edge("e3", MEM083, "read_by", D007, DAY + timedelta(days=3)),
    edge("e4", KB200, "retrieved_by", D009, DAY),
    edge("e5", KB117, "retrieved_by", D012, DAY + timedelta(days=20)),  # after the window
)
DECISIONS = {
    "decision-001": decision("decision-001", DAY),
    "decision-007": decision("decision-007", DAY + timedelta(days=3), tool_results_hash=None),
    "decision-009": decision("decision-009", DAY),
    "decision-012": decision("decision-012", DAY + timedelta(days=20)),
}


class Graph:
    def __init__(self, edges: Sequence[LineageEdge]) -> None:
        self.edges = tuple(edges)

    async def edges_from(self, n: NodeRef) -> Sequence[LineageEdge]:
        return [e for e in self.edges if e.source == n]

    async def edges_to(self, n: NodeRef) -> Sequence[LineageEdge]:
        return [e for e in self.edges if e.target == n]


class History:
    def __init__(self, decisions: dict[str, HistoricalDecision]) -> None:
        self.decisions = decisions

    async def get_decision(self, decision_id: str) -> HistoricalDecision | None:
        return self.decisions.get(decision_id)


def trigger(kind: str = "document", reference: str = "kb-117") -> RecallTrigger:
    return RecallTrigger.model_validate(
        {"trigger_id": "t1", "kind": kind, "reference": reference,
         "mode": "decision_counterfactual", "start_at": "2026-10-01T00:00:00Z",
         "end_at": "2026-10-14T00:00:00Z", "target_id": "cartwheel-fixture"}
    )  # fmt: skip


def trace(edges: Sequence[LineageEdge] = EDGES, **limits: int) -> tuple[ExposureRecord, ...]:
    scoper = RecallScoper(Graph(edges), History(DECISIONS), ScopeLimits(**limits))
    return asyncio.run(scoper.trace("recall-001", trigger())).exposures


def test_direct_and_second_order_exposure_through_memory() -> None:
    exposures = {e.decision_id: e for e in trace()}
    assert set(exposures) == {"decision-001", "decision-007"}
    assert exposures["decision-001"].direct
    second = exposures["decision-007"]
    assert not second.direct
    assert [e.relation for e in second.path] == ["retrieved_by", "wrote", "read_by"]


def test_unrelated_and_out_of_window_decisions_are_not_exposed() -> None:
    ids = {e.decision_id for e in trace()}
    assert "decision-009" not in ids, "different source"
    assert "decision-012" not in ids, "edge recorded after the incident window"


def test_hop_limit_is_reported_as_a_gap() -> None:
    scoper = RecallScoper(Graph(EDGES), History(DECISIONS), ScopeLimits(max_hops=1))
    scope = asyncio.run(scoper.trace("recall-001", trigger()))
    assert {e.decision_id for e in scope.exposures} == {"decision-001"}
    assert any("beyond 1 hops" in gap for gap in scope.gaps)


def test_edge_to_unrecorded_decision_is_a_gap_not_an_exposure() -> None:
    ghost = edge("e9", KB117, "retrieved_by", node("decision", "decision-404"), DAY)
    scoper = RecallScoper(Graph((*EDGES, ghost)), History(DECISIONS))
    scope = asyncio.run(scoper.trace("recall-001", trigger()))
    assert "decision-404" not in {e.decision_id for e in scope.exposures}
    assert any("decision-404" in gap for gap in scope.gaps)


def test_finding_triggers_are_routed_to_event_audit() -> None:
    scoper = RecallScoper(Graph(EDGES), History(DECISIONS))
    scope = asyncio.run(scoper.trace("recall-001", trigger(kind="finding", reference="f-1")))
    assert scope.exposures == () and "event audit" in scope.gaps[0]


def test_missing_tool_result_makes_decision_not_replayable() -> None:
    incoming = [e for e in EDGES if e.target == D007]
    readiness = assess_readiness(DECISIONS["decision-007"], incoming)
    assert not readiness.replayable
    assert [m.field for m in readiness.missing] == ["tool_results_hash"]


def test_fully_recorded_decision_is_replayable() -> None:
    incoming = [e for e in EDGES if e.target == D001]
    assert assess_readiness(DECISIONS["decision-001"], incoming).replayable


def test_lineage_makes_kb_snapshot_critical_even_if_recorder_said_optional() -> None:
    d = decision(
        "decision-001",
        DAY,
        kb_snapshot_hash=None,
        missing_inputs=(
            MissingInput(field="kb_snapshot_hash", reason="not captured", critical=False),
        ),
    )
    readiness = assess_readiness(d, [EDGES[0]])
    assert not readiness.replayable
    assert readiness.missing[0].critical


def test_unused_optional_snapshot_does_not_block_replay() -> None:
    d = decision("decision-001", DAY, memory_snapshot_hash=None)
    assert assess_readiness(d, [EDGES[0]]).replayable, "decision never read memory"


@pytest.mark.parametrize(
    ("source", "relation", "target"),
    [
        (D001, "retrieved_by", KB117),
        (MEM083, "wrote", D001),
        (KB117, "configured", D001),
    ],
)
def test_impossible_edges_are_rejected(source: NodeRef, relation: str, target: NodeRef) -> None:
    with pytest.raises(ValidationError):
        edge("bad", source, relation, target, DAY)


def test_exposure_path_must_be_connected_and_end_at_decision() -> None:
    good = trace()[1]
    with pytest.raises(ValidationError):
        ExposureRecord.model_validate({**good.model_dump(), "path": [good.path[0], good.path[2]]})
    with pytest.raises(ValidationError):
        ExposureRecord.model_validate({**good.model_dump(), "decision_id": "decision-009"})
    with pytest.raises(ValidationError):
        ExposureRecord.model_validate({**good.model_dump(), "direct": True})
