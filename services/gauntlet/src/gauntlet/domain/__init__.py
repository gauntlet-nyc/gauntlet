"""Pure truth policies; no provider SDK imports."""

from .errors import GauntletDomainError, IllegalTransitionError, InvalidEvidenceError
from .materiality import (
    DecisionOutcome,
    MaterialityPolicy,
    ReplayDistribution,
    distribution,
)
from .path_policy import is_patch_path_allowed, is_path_allowed
from .state import GATE_LIFECYCLE, RECALL_LIFECYCLE, GateState, RecallState, StateMachine
from .statuses import (
    CONFIRMED_GATE_STATUSES,
    Attribution,
    GateStatus,
    OracleKind,
    OracleOutcome,
    RecallClassification,
    ReplayStatus,
    Severity,
)
from .verdicts import (
    MIN_CONFIRMING_REPRODUCTIONS,
    AuditEvidence,
    ControlComparison,
    GateEvidence,
    GateVerdict,
    classify_counterfactual,
    classify_event_audit,
    classify_gate,
)

__all__ = [
    "CONFIRMED_GATE_STATUSES",
    "GATE_LIFECYCLE",
    "MIN_CONFIRMING_REPRODUCTIONS",
    "RECALL_LIFECYCLE",
    "Attribution",
    "AuditEvidence",
    "ControlComparison",
    "DecisionOutcome",
    "GateEvidence",
    "GateState",
    "GateStatus",
    "GateVerdict",
    "GauntletDomainError",
    "IllegalTransitionError",
    "InvalidEvidenceError",
    "MaterialityPolicy",
    "OracleKind",
    "OracleOutcome",
    "RecallClassification",
    "RecallState",
    "ReplayDistribution",
    "ReplayStatus",
    "Severity",
    "StateMachine",
    "classify_counterfactual",
    "classify_event_audit",
    "classify_gate",
    "distribution",
    "is_patch_path_allowed",
    "is_path_allowed",
]
