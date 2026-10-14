"""Canonical verdict and status vocabularies. Stdlib only; contracts re-use these enums."""

from enum import StrEnum


class GateStatus(StrEnum):
    CONFIRMED_REGRESSION = "confirmed_regression"
    CONFIRMED_PRE_EXISTING = "confirmed_pre_existing"
    CONFIRMED_POLICY_VIOLATION = "confirmed_policy_violation"
    SUSPECTED = "suspected"
    NOT_REPRODUCIBLE = "not_reproducible"
    ENVIRONMENT_ERROR = "environment_error"
    PASSED = "passed"
    NOT_TESTED = "not_tested"


class Attribution(StrEnum):
    INTRODUCED = "introduced"
    PRE_EXISTING = "pre_existing"
    UNKNOWN = "unknown"


class RecallClassification(StrEnum):
    AUDIT_VIOLATION = "audit_violation"
    AUDIT_CLEAR = "audit_clear"
    TAINTED = "tainted"
    CLEARED = "cleared"
    INCONCLUSIVE = "inconclusive"
    NOT_REPLAYABLE = "not_replayable"


class OracleOutcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"


class ReplayStatus(StrEnum):
    MATCHED = "matched"
    DIFFERENT = "different"
    INCONCLUSIVE = "inconclusive"
    NOT_REPLAYABLE = "not_replayable"
    ENVIRONMENT_ERROR = "environment_error"


class OracleKind(StrEnum):
    """Master plan Section 8.2 priorities. Only HARD oracles may confirm a Gate finding."""

    HARD = "hard"
    DIFFERENTIAL = "differential"
    SEMANTIC_JUDGE = "semantic_judge"
    MODEL_ONLY = "model_only"


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


CONFIRMED_GATE_STATUSES: frozenset[GateStatus] = frozenset(
    {
        GateStatus.CONFIRMED_REGRESSION,
        GateStatus.CONFIRMED_PRE_EXISTING,
        GateStatus.CONFIRMED_POLICY_VIOLATION,
    }
)
