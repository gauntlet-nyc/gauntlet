"""Run lifecycles: only planned transitions, abort from any active state, nothing after terminal."""

import pytest
from gauntlet.domain import (
    GATE_LIFECYCLE,
    RECALL_LIFECYCLE,
    GateState,
    IllegalTransitionError,
    RecallState,
)

GATE_HAPPY_PATH = [
    GateState.CREATED, GateState.INTAKE, GateState.IMPACT_MAPPED, GateState.PLANNED,
    GateState.SCOPE_PENDING, GateState.PROVISIONING, GateState.EXECUTING, GateState.VERIFYING,
    GateState.FINDINGS_READY, GateState.FIX_PENDING, GateState.FIX_APPROVED, GateState.PATCHING,
    GateState.RETESTING, GateState.RELEASE_REVIEW, GateState.READY_FOR_REVIEW,
]  # fmt: skip


def test_gate_happy_path_is_connected() -> None:
    for current, target in zip(GATE_HAPPY_PATH, GATE_HAPPY_PATH[1:], strict=False):
        assert GATE_LIFECYCLE.require(current, target) is target


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (GateState.PLANNED, GateState.EXECUTING),  # cannot skip scope approval
        (GateState.FINDINGS_READY, GateState.PATCHING),  # cannot patch without fix approval
        (GateState.FIX_PENDING, GateState.PATCHING),
        (GateState.EXECUTING, GateState.READY_FOR_REVIEW),
    ],
)
def test_gate_cannot_skip_human_gates(current: GateState, target: GateState) -> None:
    with pytest.raises(IllegalTransitionError):
        GATE_LIFECYCLE.require(current, target)


def test_every_active_state_can_cancel_or_fail() -> None:
    for state in GateState:
        if not GATE_LIFECYCLE.is_terminal(state):
            assert {GateState.CANCELLED, GateState.FAILED} <= GATE_LIFECYCLE.allowed(state)


@pytest.mark.parametrize(
    "terminal",
    [GateState.READY_FOR_REVIEW, GateState.HELD, GateState.INCONCLUSIVE, GateState.CANCELLED],
)
def test_terminal_gate_states_are_final(terminal: GateState) -> None:
    assert GATE_LIFECYCLE.is_terminal(terminal)
    with pytest.raises(IllegalTransitionError):
        GATE_LIFECYCLE.require(terminal, GateState.CANCELLED)


def test_no_state_means_merged_or_released() -> None:
    assert not {s for s in GateState if "merge" in s or "release" == s or "deploy" in s}


def test_every_gate_state_is_reachable_from_created() -> None:
    seen = {GateState.CREATED}
    frontier = [GateState.CREATED]
    while frontier:
        for nxt in GATE_LIFECYCLE.allowed(frontier.pop()):
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    assert seen == set(GateState)


def test_recall_counterfactual_and_audit_paths() -> None:
    path = [
        RecallState.CREATED, RecallState.TRIGGER_VALIDATED, RecallState.LINEAGE_SCOPED,
        RecallState.SCOPE_PENDING, RecallState.BUILDING_REPLAY_SPECS,
        RecallState.REPLAYING_CONTROL, RecallState.REPLAYING_COUNTERFACTUAL,
        RecallState.CLASSIFYING, RecallState.REMEDIATION_DRAFTS, RecallState.REVIEW_PENDING,
        RecallState.REVIEWED, RecallState.CLOSED,
    ]  # fmt: skip
    for current, target in zip(path, path[1:], strict=False):
        RECALL_LIFECYCLE.require(current, target)
    RECALL_LIFECYCLE.require(RecallState.SCOPE_PENDING, RecallState.AUDITING)
    RECALL_LIFECYCLE.require(RecallState.REPLAYING_CONTROL, RecallState.CLASSIFYING)


def test_recall_cannot_counterfactual_before_control() -> None:
    with pytest.raises(IllegalTransitionError):
        RECALL_LIFECYCLE.require(
            RecallState.BUILDING_REPLAY_SPECS, RecallState.REPLAYING_COUNTERFACTUAL
        )
