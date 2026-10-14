"""Minimal pure verdict classifier samples, not an implemented end-to-end verifier."""

from dataclasses import dataclass
from typing import Literal

GateClassification = Literal[
    "confirmed_regression", "confirmed_pre_existing", "not_reproducible",
    "environment_error", "passed",
]
RecallClassification = Literal["tainted", "cleared", "inconclusive", "not_replayable"]


@dataclass(frozen=True)
class GateOracleComparison:
    head_failed: bool
    base_failed: bool
    head_reproduced: bool
    fixtures_equal: bool
    environment_ok: bool


def classify_gate(value: GateOracleComparison) -> GateClassification:
    if not value.environment_ok or not value.fixtures_equal:
        return "environment_error"
    if value.head_failed and not value.head_reproduced:
        return "not_reproducible"
    if value.head_failed and value.base_failed:
        return "confirmed_pre_existing"
    if value.head_failed:
        return "confirmed_regression"
    return "passed"


@dataclass(frozen=True)
class ControlComparison:
    critical_inputs_present: bool
    control_matches_original: bool
    material_change: bool | None


def classify_counterfactual(value: ControlComparison) -> RecallClassification:
    if not value.critical_inputs_present:
        return "not_replayable"
    if not value.control_matches_original or value.material_change is None:
        return "inconclusive"
    return "tainted" if value.material_change else "cleared"
