from gauntlet.domain.verdicts import (
    ControlComparison,
    GateOracleComparison,
    classify_counterfactual,
    classify_gate,
)


def test_gate_head_only_fail_is_regression() -> None:
    assert classify_gate(GateOracleComparison(True, False, True, True, True)) == "confirmed_regression"


def test_gate_both_fail_is_pre_existing() -> None:
    assert classify_gate(GateOracleComparison(True, True, True, True, True)) == "confirmed_pre_existing"


def test_gate_mismatched_fixture_is_not_a_regression() -> None:
    assert classify_gate(GateOracleComparison(True, False, True, False, True)) == "environment_error"


def test_counterfactual_control_mismatch_is_inconclusive() -> None:
    assert classify_counterfactual(ControlComparison(True, False, True)) == "inconclusive"


def test_counterfactual_missing_inputs_not_replayable() -> None:
    assert classify_counterfactual(ControlComparison(False, True, True)) == "not_replayable"


def test_counterfactual_material_delta_is_tainted() -> None:
    assert classify_counterfactual(ControlComparison(True, True, True)) == "tainted"


def test_counterfactual_clean_outcome_is_cleared() -> None:
    assert classify_counterfactual(ControlComparison(True, True, False)) == "cleared"
