"""Pure Gate and Recall verdict policies (master plan Section 5.1). No I/O, no provider imports."""

from dataclasses import dataclass

from .errors import InvalidEvidenceError
from .statuses import Attribution, GateStatus, RecallClassification

MIN_CONFIRMING_REPRODUCTIONS = 2
"""A hard-oracle failure must reproduce at least this many times on head to be confirmed."""


@dataclass(frozen=True)
class GateEvidence:
    """Aggregated head/base oracle results for one frozen attack spec."""

    environment_ok: bool
    fixtures_equal: bool
    oracle_trusted: bool
    head_attempts: int
    head_failures: int
    base_attempts: int
    base_failures: int

    def __post_init__(self) -> None:
        for attempts, failures, side in (
            (self.head_attempts, self.head_failures, "head"),
            (self.base_attempts, self.base_failures, "base"),
        ):
            if attempts < 0 or failures < 0:
                raise InvalidEvidenceError(f"{side} counts must be non-negative")
            if failures > attempts:
                raise InvalidEvidenceError(f"{side} failures exceed attempts")


@dataclass(frozen=True)
class GateVerdict:
    status: GateStatus
    attribution: Attribution


def classify_gate(evidence: GateEvidence) -> GateVerdict:
    if not evidence.environment_ok or not evidence.fixtures_equal:
        return GateVerdict(GateStatus.ENVIRONMENT_ERROR, Attribution.UNKNOWN)
    if evidence.head_attempts == 0:
        return GateVerdict(GateStatus.NOT_TESTED, Attribution.UNKNOWN)
    if evidence.head_failures == 0:
        return GateVerdict(GateStatus.PASSED, Attribution.UNKNOWN)
    if not evidence.oracle_trusted:
        return GateVerdict(GateStatus.SUSPECTED, Attribution.UNKNOWN)
    if evidence.head_failures < MIN_CONFIRMING_REPRODUCTIONS:
        if evidence.head_attempts < MIN_CONFIRMING_REPRODUCTIONS:
            return GateVerdict(GateStatus.SUSPECTED, Attribution.UNKNOWN)
        return GateVerdict(GateStatus.NOT_REPRODUCIBLE, Attribution.UNKNOWN)
    if evidence.base_attempts == 0:
        return GateVerdict(GateStatus.CONFIRMED_POLICY_VIOLATION, Attribution.UNKNOWN)
    if evidence.base_failures > 0:
        return GateVerdict(GateStatus.CONFIRMED_PRE_EXISTING, Attribution.PRE_EXISTING)
    return GateVerdict(GateStatus.CONFIRMED_REGRESSION, Attribution.INTRODUCED)


@dataclass(frozen=True)
class ControlComparison:
    """Original vs control vs counterfactual replay comparison for one historical decision."""

    critical_inputs_present: bool
    environment_ok: bool
    control_matches_original: bool
    material_change: bool | None


def classify_counterfactual(value: ControlComparison) -> RecallClassification:
    if not value.critical_inputs_present:
        return RecallClassification.NOT_REPLAYABLE
    if not value.environment_ok or not value.control_matches_original:
        return RecallClassification.INCONCLUSIVE
    if value.material_change is None:
        return RecallClassification.INCONCLUSIVE
    return RecallClassification.TAINTED if value.material_change else RecallClassification.CLEARED


@dataclass(frozen=True)
class AuditEvidence:
    """Deterministic event-audit facts. A caller/owner mismatch alone is not a forbidden effect."""

    relevant_logs_complete: bool
    authoritative_state_checked: bool
    forbidden_effect_confirmed: bool


def classify_event_audit(value: AuditEvidence) -> RecallClassification:
    if not value.relevant_logs_complete or not value.authoritative_state_checked:
        return RecallClassification.INCONCLUSIVE
    if value.forbidden_effect_confirmed:
        return RecallClassification.AUDIT_VIOLATION
    return RecallClassification.AUDIT_CLEAR
