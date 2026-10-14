"""Gate and Recall run lifecycles (master plan Section 3.3). There is no released/merged state."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from .errors import IllegalTransitionError


class GateState(StrEnum):
    CREATED = "created"
    INTAKE = "intake"
    IMPACT_MAPPED = "impact_mapped"
    PLANNED = "planned"
    SCOPE_PENDING = "scope_pending"
    PROVISIONING = "provisioning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    FINDINGS_READY = "findings_ready"
    FIX_PENDING = "fix_pending"
    FIX_APPROVED = "fix_approved"
    PATCHING = "patching"
    RETESTING = "retesting"
    RELEASE_REVIEW = "release_review"
    READY_FOR_REVIEW = "ready_for_review"
    HELD = "held"
    INCONCLUSIVE = "inconclusive"
    CANCELLED = "cancelled"
    FAILED = "failed"


class RecallState(StrEnum):
    CREATED = "created"
    TRIGGER_VALIDATED = "trigger_validated"
    LINEAGE_SCOPED = "lineage_scoped"
    SCOPE_PENDING = "scope_pending"
    AUDITING = "auditing"
    BUILDING_REPLAY_SPECS = "building_replay_specs"
    REPLAYING_CONTROL = "replaying_control"
    REPLAYING_COUNTERFACTUAL = "replaying_counterfactual"
    CLASSIFYING = "classifying"
    REMEDIATION_DRAFTS = "remediation_drafts"
    REVIEW_PENDING = "review_pending"
    REVIEWED = "reviewed"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True)
class StateMachine[S: StrEnum]:
    name: str
    transitions: Mapping[S, frozenset[S]]
    abort_states: frozenset[S]
    """Reachable from every non-terminal state (cancellation, unrecoverable error)."""

    def is_terminal(self, state: S) -> bool:
        return not self.transitions.get(state)

    def allowed(self, current: S) -> frozenset[S]:
        if self.is_terminal(current):
            return frozenset()
        return self.transitions[current] | self.abort_states

    def require(self, current: S, target: S) -> S:
        if target not in self.allowed(current):
            raise IllegalTransitionError(f"{self.name}: {current} -> {target} is not allowed")
        return target


_G = GateState
GATE_LIFECYCLE: StateMachine[GateState] = StateMachine(
    name="gate",
    transitions={
        _G.CREATED: frozenset({_G.INTAKE}),
        _G.INTAKE: frozenset({_G.IMPACT_MAPPED}),
        _G.IMPACT_MAPPED: frozenset({_G.PLANNED}),
        _G.PLANNED: frozenset({_G.SCOPE_PENDING, _G.RELEASE_REVIEW}),
        _G.SCOPE_PENDING: frozenset({_G.PROVISIONING, _G.HELD}),
        _G.PROVISIONING: frozenset({_G.EXECUTING}),
        _G.EXECUTING: frozenset({_G.VERIFYING}),
        _G.VERIFYING: frozenset({_G.FINDINGS_READY}),
        _G.FINDINGS_READY: frozenset({_G.FIX_PENDING, _G.RELEASE_REVIEW}),
        _G.FIX_PENDING: frozenset({_G.FIX_APPROVED, _G.FINDINGS_READY}),
        _G.FIX_APPROVED: frozenset({_G.PATCHING}),
        _G.PATCHING: frozenset({_G.RETESTING}),
        _G.RETESTING: frozenset({_G.FINDINGS_READY, _G.RELEASE_REVIEW}),
        _G.RELEASE_REVIEW: frozenset({_G.READY_FOR_REVIEW, _G.HELD, _G.INCONCLUSIVE}),
    },
    abort_states=frozenset({_G.CANCELLED, _G.FAILED}),
)

_R = RecallState
RECALL_LIFECYCLE: StateMachine[RecallState] = StateMachine(
    name="recall",
    transitions={
        _R.CREATED: frozenset({_R.TRIGGER_VALIDATED}),
        _R.TRIGGER_VALIDATED: frozenset({_R.LINEAGE_SCOPED}),
        _R.LINEAGE_SCOPED: frozenset({_R.SCOPE_PENDING}),
        _R.SCOPE_PENDING: frozenset({_R.AUDITING, _R.BUILDING_REPLAY_SPECS, _R.CLOSED}),
        _R.AUDITING: frozenset({_R.CLASSIFYING}),
        _R.BUILDING_REPLAY_SPECS: frozenset({_R.REPLAYING_CONTROL, _R.CLASSIFYING}),
        _R.REPLAYING_CONTROL: frozenset({_R.REPLAYING_COUNTERFACTUAL, _R.CLASSIFYING}),
        _R.REPLAYING_COUNTERFACTUAL: frozenset({_R.CLASSIFYING}),
        _R.CLASSIFYING: frozenset({_R.REMEDIATION_DRAFTS, _R.REVIEW_PENDING}),
        _R.REMEDIATION_DRAFTS: frozenset({_R.REVIEW_PENDING}),
        _R.REVIEW_PENDING: frozenset({_R.REVIEWED}),
        _R.REVIEWED: frozenset({_R.CLOSED}),
    },
    abort_states=frozenset({_R.CANCELLED, _R.FAILED}),
)
