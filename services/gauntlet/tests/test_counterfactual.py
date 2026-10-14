"""A-06 / Phase 6 gate: one confirmed flip, one unaffected exposed decision, one control
mismatch and one missing-state case; nondeterminism is never a verdict."""

import asyncio
from datetime import UTC, datetime

import pytest
from gauntlet.application.recall import (
    CounterfactualSettings,
    CounterfactualUseCase,
    ReplayReadiness,
    assess_readiness,
)
from gauntlet.contracts import (
    ExposureRecord,
    HistoricalDecision,
    LineageEdge,
    NodeRef,
    RecallVerdict,
    ReplayResult,
    ReplaySpec,
)
from gauntlet.domain import (
    DecisionOutcome,
    MaterialityPolicy,
    RecallClassification,
    ReplayStatus,
    distribution,
)
from gauntlet.ports import ReplayWorld

T = datetime(2026, 10, 5, 10, 0, tzinfo=UTC)
HASH = "ab" * 32
KB117 = NodeRef(kind="document_chunk", node_id="kb-117")
REFUND = ("start_refund", 4999)
DECLINE = ("decline_refund", None)
WORLD = ReplayWorld(source_sha="cccccccc", fixture_id="history-2026-10-05", fixture_checksum=HASH)


def decision(decision_id: str, **overrides: object) -> HistoricalDecision:
    fields: dict[str, object] = {
        "decision_id": decision_id, "target_id": "cartwheel-fixture", "occurred_at": T,
        "agent_id": "support-agent", "actor_ref": "synthetic-customer-17",
        "model_id": "example-model-id", "prompt_version": "support-v3",
        "policy_version": "refund-policy-7", "tool_results_hash": HASH,
        "kb_snapshot_hash": HASH, "memory_snapshot_hash": HASH, "input_messages_hash": HASH,
        "structured_action": "start_refund", "amount_minor": 4999,
    }  # fmt: skip
    fields.update(overrides)
    return HistoricalDecision.model_validate(fields)


def exposure(decision_id: str, trigger: NodeRef = KB117) -> ExposureRecord:
    edge = LineageEdge.model_validate(
        {"edge_id": f"e-{decision_id}", "source": trigger,
         "relation": "retrieved_by" if trigger.kind == "document_chunk" else "configured",
         "target": {"kind": "decision", "node_id": decision_id}, "recorded_at": T}
    )  # fmt: skip
    return ExposureRecord(
        exposure_id=f"r:{decision_id}", recall_id="recall-001", decision_id=decision_id,
        trigger_node=trigger, path=(edge,), direct=True,
    )  # fmt: skip


Outcome = tuple[str | None, int | None]


class ScriptedReplay:
    """Per decision and arm, a list of outcomes (one per run) or a status to return."""

    def __init__(self, script: dict[tuple[str, str], list[Outcome] | str]) -> None:
        self.script = script
        self.specs: list[ReplaySpec] = []

    async def replay(self, spec: ReplaySpec) -> ReplayResult:
        self.specs.append(spec)
        arm = "counterfactual" if spec.mode == "historical_counterfactual" else "control"
        entry = self.script[(spec.decision_id or "", arm)]
        if isinstance(entry, str):
            return ReplayResult(replay_id=spec.replay_id, status=ReplayStatus(entry))
        action, amount = entry[spec.seed or 0]
        return ReplayResult(
            replay_id=spec.replay_id,
            status=ReplayStatus.MATCHED,
            observed_action=action,
            amount_minor=amount,
        )


class Worlds:
    def __init__(self, world: ReplayWorld | None = WORLD) -> None:
        self.world = world

    async def world_for(self, decision: HistoricalDecision) -> ReplayWorld | None:
        return self.world


def run(
    script: dict[tuple[str, str], list[Outcome] | str],
    d: HistoricalDecision,
    readiness: ReplayReadiness | None = None,
    worlds: Worlds | None = None,
    trigger: NodeRef = KB117,
) -> tuple[RecallVerdict, ScriptedReplay]:
    engine = ScriptedReplay(script)
    use_case = CounterfactualUseCase(engine, worlds or Worlds(), CounterfactualSettings(repeats=3))
    exp = exposure(d.decision_id, trigger)
    ready = readiness or assess_readiness(d, exp.path)
    return asyncio.run(use_case.evaluate("recall-001", exp, d, ready)), engine


def test_confirmed_flip_is_tainted() -> None:
    verdict, engine = run(
        {("d1", "control"): [REFUND] * 3, ("d1", "counterfactual"): [DECLINE] * 3},
        decision("d1"),
    )
    assert verdict.classification is RecallClassification.TAINTED
    assert verdict.control_matches is True and verdict.material_change is True
    assert len(verdict.replay_ids) == 6
    assert "decline_refund" in verdict.rationale


def test_unaffected_exposed_decision_is_cleared() -> None:
    verdict, _ = run(
        {("d2", "control"): [REFUND] * 3, ("d2", "counterfactual"): [REFUND] * 3},
        decision("d2"),
    )
    assert verdict.classification is RecallClassification.CLEARED
    assert verdict.material_change is False


def test_control_mismatch_is_inconclusive_and_counterfactual_never_runs() -> None:
    verdict, engine = run(
        {("d3", "control"): [DECLINE] * 3, ("d3", "counterfactual"): [DECLINE] * 3},
        decision("d3"),
    )
    assert verdict.classification is RecallClassification.INCONCLUSIVE
    assert verdict.control_matches is False
    assert all(s.mode == "historical_control" for s in engine.specs)


def test_missing_state_is_not_replayable_without_any_replay() -> None:
    d = decision("d4", tool_results_hash=None)
    verdict, engine = run({}, d)
    assert verdict.classification is RecallClassification.NOT_REPLAYABLE
    assert "tool_results_hash" in verdict.rationale
    assert engine.specs == []


def test_unstable_control_is_inconclusive() -> None:
    verdict, _ = run(
        {("d5", "control"): [REFUND, REFUND, DECLINE], ("d5", "counterfactual"): [DECLINE] * 3},
        decision("d5"),
    )
    assert verdict.classification is RecallClassification.INCONCLUSIVE


def test_unstable_counterfactual_is_inconclusive_not_tainted() -> None:
    verdict, _ = run(
        {("d6", "control"): [REFUND] * 3, ("d6", "counterfactual"): [DECLINE, REFUND, DECLINE]},
        decision("d6"),
    )
    assert verdict.classification is RecallClassification.INCONCLUSIVE
    assert verdict.control_matches is True and verdict.material_change is None


def test_replay_environment_failure_is_inconclusive() -> None:
    verdict, _ = run(
        {("d7", "control"): [REFUND] * 3, ("d7", "counterfactual"): "environment_error"},
        decision("d7"),
    )
    assert verdict.classification is RecallClassification.INCONCLUSIVE


def test_unreconstructable_world_is_not_replayable() -> None:
    verdict, _ = run({}, decision("d8"), worlds=Worlds(None))
    assert verdict.classification is RecallClassification.NOT_REPLAYABLE


def test_version_trigger_without_mutation_is_inconclusive() -> None:
    model = NodeRef(kind="model_version", node_id="model-2026-09")
    d = decision("d9")
    edge = LineageEdge.model_validate(
        {"edge_id": "e", "source": model, "relation": "configured",
         "target": {"kind": "decision", "node_id": "d9"}, "recorded_at": T}
    )  # fmt: skip
    verdict, engine = run({}, d, readiness=assess_readiness(d, [edge]), trigger=model)
    assert verdict.classification is RecallClassification.INCONCLUSIVE
    assert engine.specs == []


def test_specs_pin_inputs_and_mutate_only_the_trigger() -> None:
    _, engine = run(
        {("d1", "control"): [REFUND] * 3, ("d1", "counterfactual"): [DECLINE] * 3},
        decision("d1"),
    )
    control = [s for s in engine.specs if s.mode == "historical_control"]
    counter = [s for s in engine.specs if s.mode == "historical_counterfactual"]
    assert all(s.excluded_source_id is None for s in control)
    assert all(s.excluded_source_id == "kb-117" for s in counter)
    pinned = {
        (s.tool_results_hash, s.input_messages_hash, s.fixture_checksum) for s in engine.specs
    }
    assert pinned == {(HASH, HASH, HASH)}
    assert [s.seed for s in control] == [0, 1, 2]


def test_single_run_settings_are_refused() -> None:
    with pytest.raises(ValueError, match="nondeterminism"):
        CounterfactualUseCase(ScriptedReplay({}), Worlds(), CounterfactualSettings(repeats=1))


@pytest.mark.parametrize(
    ("a", "b", "tolerance", "differs"),
    [
        (("refund", 4999), ("refund", 4999), 0, False),
        (("refund", 4999), ("refund", 5000), 0, True),
        (("refund", 4999), ("refund", 5000), 1, False),
        (("refund", 4999), ("decline", 4999), 100, True),
        (("refund", None), ("refund", 0), 0, True),
    ],
)
def test_materiality_policy(a: Outcome, b: Outcome, tolerance: int, differs: bool) -> None:
    policy = MaterialityPolicy(amount_tolerance_minor=tolerance)
    assert policy.differs(DecisionOutcome(*a), DecisionOutcome(*b)) is differs


def test_empty_distribution_is_unstable() -> None:
    assert not distribution([], MaterialityPolicy()).stable
