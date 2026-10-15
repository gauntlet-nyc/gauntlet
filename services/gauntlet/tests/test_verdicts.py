import pytest

from gauntlet.domain import (
    Attribution,
    AuditEvidence,
    ControlComparison,
    GateEvidence,
    GateStatus,
    GateVerdict,
    InvalidEvidenceError,
    RecallClassification,
    classify_counterfactual,
    classify_event_audit,
    classify_gate,
)


def gate(**overrides: int | bool) -> GateVerdict:
    fields: dict[str, int | bool] = {
        "environment_ok": True,
        "fixtures_equal": True,
        "oracle_trusted": True,
        "head_attempts": 3,
        "head_failures": 3,
        "base_attempts": 3,
        "base_failures": 0,
    }
    fields.update(overrides)
    return classify_gate(GateEvidence(**fields))  # type: ignore[arg-type]


def test_head_only_failure_is_introduced_regression() -> None:
    assert gate() == GateVerdict(GateStatus.CONFIRMED_REGRESSION, Attribution.INTRODUCED)


def test_both_fail_is_pre_existing() -> None:
    assert gate(base_failures=2) == GateVerdict(
        GateStatus.CONFIRMED_PRE_EXISTING, Attribution.PRE_EXISTING
    )


def test_no_base_run_is_policy_violation_with_unknown_attribution() -> None:
    assert gate(base_attempts=0) == GateVerdict(
        GateStatus.CONFIRMED_POLICY_VIOLATION, Attribution.UNKNOWN
    )


@pytest.mark.parametrize("override", [{"fixtures_equal": False}, {"environment_ok": False}])
def test_bad_environment_is_never_a_regression(override: dict[str, bool]) -> None:
    assert gate(**override).status is GateStatus.ENVIRONMENT_ERROR


def test_model_only_oracle_cannot_confirm() -> None:
    assert gate(oracle_trusted=False).status is GateStatus.SUSPECTED


def test_single_failure_without_retry_is_suspected() -> None:
    assert gate(head_attempts=1, head_failures=1).status is GateStatus.SUSPECTED


def test_single_failure_after_retries_is_not_reproducible() -> None:
    assert gate(head_attempts=3, head_failures=1).status is GateStatus.NOT_REPRODUCIBLE


def test_clean_head_passes_and_unrun_head_is_not_tested() -> None:
    assert gate(head_failures=0).status is GateStatus.PASSED
    assert gate(head_attempts=0, head_failures=0).status is GateStatus.NOT_TESTED


def test_impossible_counts_are_rejected() -> None:
    with pytest.raises(InvalidEvidenceError):
        GateEvidence(
            True, True, True, head_attempts=1, head_failures=2, base_attempts=0, base_failures=0
        )


def cf(**overrides: bool | None) -> RecallClassification:
    fields: dict[str, bool | None] = {
        "critical_inputs_present": True,
        "environment_ok": True,
        "control_matches_original": True,
        "material_change": True,
    }
    fields.update(overrides)
    return classify_counterfactual(ControlComparison(**fields))  # type: ignore[arg-type]


def test_counterfactual_material_delta_is_tainted() -> None:
    assert cf() is RecallClassification.TAINTED


def test_counterfactual_no_delta_is_cleared() -> None:
    assert cf(material_change=False) is RecallClassification.CLEARED


def test_counterfactual_missing_inputs_not_replayable() -> None:
    assert cf(critical_inputs_present=False) is RecallClassification.NOT_REPLAYABLE


@pytest.mark.parametrize(
    "override",
    [{"control_matches_original": False}, {"environment_ok": False}, {"material_change": None}],
)
def test_counterfactual_uncertainty_is_inconclusive(override: dict[str, bool | None]) -> None:
    assert cf(**override) is RecallClassification.INCONCLUSIVE


def test_audit_confirmed_effect_with_complete_logs_is_violation() -> None:
    assert (
        classify_event_audit(AuditEvidence(True, True, True))
        is RecallClassification.AUDIT_VIOLATION
    )


def test_audit_complete_and_clean_is_clear() -> None:
    assert (
        classify_event_audit(AuditEvidence(True, True, False)) is RecallClassification.AUDIT_CLEAR
    )


@pytest.mark.parametrize(
    "evidence", [AuditEvidence(False, True, True), AuditEvidence(True, False, False)]
)
def test_audit_incomplete_evidence_is_inconclusive(evidence: AuditEvidence) -> None:
    assert classify_event_audit(evidence) is RecallClassification.INCONCLUSIVE
