"""Offline schema tests. Do not need SDK credentials."""

import pytest
from pydantic import ValidationError

from gauntlet.contracts.gate import ActionStep, AttackSpec, SourceRef
from gauntlet.contracts.recall import RecallTrigger


def test_attack_spec_rejects_unknown_action() -> None:
    with pytest.raises(ValidationError):
        ActionStep(action="run_shell", value="cat .env")  # type: ignore[arg-type]


def test_attack_budget_rejects_too_many_steps() -> None:
    with pytest.raises(ValidationError):
        AttackSpec(
            attack_id="a1",
            hypothesis="Button may obstruct another action",
            why_this_change="changed fixed positioning",
            source_refs=(SourceRef(path="web/help.tsx", sha="1234567", start_line=10, end_line=10),),
            worker_kind="ui", target_id="fixture", fixture_id="seed",
            steps=(ActionStep(action="resize", width=375, height=812), ActionStep(action="capture")),
            oracle_ids=("ui.primary_action_reachable",),
            max_actions=1,
            max_runtime_seconds=10,
        )


def test_recall_trigger_serializes() -> None:
    trigger = RecallTrigger.model_validate({
        "trigger_id": "t1", "kind": "document", "reference": "kb-117",
        "mode": "decision_counterfactual", "start_at": "2026-10-01T00:00:00Z",
        "end_at": "2026-10-14T00:00:00Z", "target_id": "demo",
    })
    assert trigger.reference == "kb-117"
