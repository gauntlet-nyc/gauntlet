"""Offline contract invariants. Each test starts from a valid golden and breaks one rule."""

import json
from pathlib import Path

import pytest
from gauntlet.contracts import (
    AttackSpec,
    Finding,
    RecallTrigger,
    RecallVerdict,
    ReplaySpec,
    RunEvent,
    SourceRef,
)
from pydantic import ValidationError

EXAMPLES_DIR = Path(__file__).resolve().parents[3] / "docs" / "contracts" / "examples"


def golden(name: str, **overrides: object) -> dict[str, object]:
    data: dict[str, object] = json.loads((EXAMPLES_DIR / name).read_text(encoding="utf-8"))
    data.update(overrides)
    return data


def ui_plan_with_steps(*steps: dict[str, object]) -> dict[str, object]:
    return golden("ui-plan.v1.json", steps=list(steps))


# --- Attack plans: typed, bounded, no free-form execution ---------------------------------


def test_unknown_action_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AttackSpec.model_validate(ui_plan_with_steps({"action": "run_shell", "value": "cat .env"}))


@pytest.mark.parametrize(
    "path",
    [
        "https://evil.example/x",
        "//evil.example/x",
        "javascript:alert(1)",
        "/a/../../etc",
        "/checkout/%2e%2e/admin",
        "/checkout/..%2Fadmin",
        "/checkout/%252e%252e/admin",
        "/checkout/./x",
        "/checkout/a b",
    ],
)
def test_navigate_only_accepts_origin_relative_routes(path: str) -> None:
    with pytest.raises(ValidationError):
        AttackSpec.model_validate(ui_plan_with_steps({"action": "navigate", "path": path}))


def test_resize_requires_dimensions() -> None:
    with pytest.raises(ValidationError):
        AttackSpec.model_validate(ui_plan_with_steps({"action": "resize"}))


def test_step_rejects_fields_from_other_actions() -> None:
    with pytest.raises(ValidationError):
        AttackSpec.model_validate(
            ui_plan_with_steps({"action": "click", "target": "x", "value": "extra"})
        )


def test_steps_cannot_exceed_action_budget() -> None:
    with pytest.raises(ValidationError):
        AttackSpec.model_validate(golden("ui-plan.v1.json", max_actions=1))


def test_oracle_ids_must_be_registered_style_and_unique() -> None:
    with pytest.raises(ValidationError):
        AttackSpec.model_validate(golden("ui-plan.v1.json", oracle_ids=["lambda: True"]))
    with pytest.raises(ValidationError):
        AttackSpec.model_validate(
            golden("ui-plan.v1.json", oracle_ids=["ui.reachable", "ui.reachable"])
        )


@pytest.mark.parametrize("path", ["/etc/passwd", "../secrets.env", "web/./a.ts", "C:\\x.ts"])
def test_source_ref_paths_stay_inside_repository(path: str) -> None:
    with pytest.raises(ValidationError):
        SourceRef(path=path, sha="1234567", start_line=1, end_line=1)


def test_source_ref_line_range_ordered() -> None:
    with pytest.raises(ValidationError):
        SourceRef(path="web/a.ts", sha="1234567", start_line=10, end_line=9)


# --- Gate findings cannot claim more than the evidence supports ---------------------------


def test_regression_with_failing_base_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Finding.model_validate(golden("finding.v1.json", base_reproductions=1))


def test_confirmed_finding_needs_repeated_reproduction() -> None:
    with pytest.raises(ValidationError):
        Finding.model_validate(golden("finding.v1.json", head_reproductions=1))


def test_confirmed_finding_needs_evidence() -> None:
    with pytest.raises(ValidationError):
        Finding.model_validate(golden("finding.v1.json", evidence_ids=[]))


def test_reproductions_cannot_exceed_attempts() -> None:
    with pytest.raises(ValidationError):
        Finding.model_validate(golden("finding.v1.json", status="suspected", head_attempts=2))


# --- Recall verdicts and replays ---------------------------------------------------------


def test_tainted_requires_matching_control() -> None:
    with pytest.raises(ValidationError):
        RecallVerdict.model_validate(
            golden("recall-verdict-tainted.v1.json", control_matches=False)
        )


def test_cleared_requires_no_material_change() -> None:
    with pytest.raises(ValidationError):
        RecallVerdict.model_validate(
            golden("recall-verdict-tainted.v1.json", classification="cleared")
        )


def test_audit_mode_cannot_produce_tainted() -> None:
    with pytest.raises(ValidationError):
        RecallVerdict.model_validate(
            golden(
                "recall-verdict-tainted.v1.json",
                mode="event_audit",
                control_matches=None,
                material_change=None,
            )
        )


def test_audit_violation_requires_evidence() -> None:
    with pytest.raises(ValidationError):
        RecallVerdict.model_validate(
            golden(
                "recall-verdict.v1.json",
                mode="event_audit",
                classification="audit_violation",
                control_matches=None,
                material_change=None,
                evidence_ids=[],
            )
        )


def test_counterfactual_must_name_mutation() -> None:
    with pytest.raises(ValidationError):
        ReplaySpec.model_validate(
            golden("replay-spec-counterfactual.v1.json", mutation_description=None)
        )


def test_control_replay_cannot_exclude_sources() -> None:
    with pytest.raises(ValidationError):
        ReplaySpec.model_validate(
            golden("replay-spec-control.v1.json", excluded_source_id="kb-117")
        )


def test_historical_replay_requires_decision() -> None:
    with pytest.raises(ValidationError):
        ReplaySpec.model_validate(golden("replay-spec-control.v1.json", decision_id=None))


def test_trigger_window_must_be_ordered() -> None:
    with pytest.raises(ValidationError):
        RecallTrigger.model_validate(
            golden("recall-trigger.v1.json", end_at="2026-09-30T00:00:00Z")
        )


def test_naive_timestamps_are_rejected() -> None:
    with pytest.raises(ValidationError):
        RecallTrigger.model_validate(
            golden("recall-trigger.v1.json", start_at="2026-10-01T00:00:00")
        )


# --- Events ------------------------------------------------------------------------------


def test_event_type_is_snake_case_identifier() -> None:
    with pytest.raises(ValidationError):
        RunEvent.model_validate(golden("run-event.v1.json", event_type="Plan Frozen!"))


def test_event_payload_is_flat() -> None:
    with pytest.raises(ValidationError):
        RunEvent.model_validate(golden("run-event.v1.json", payload={"nested": {"a": 1}}))


def test_contracts_are_immutable() -> None:
    event = RunEvent.model_validate(golden("run-event.v1.json"))
    with pytest.raises(ValidationError):
        event.sequence = 2
