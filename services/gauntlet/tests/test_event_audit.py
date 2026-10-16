"""A-05 / Phase 5 gate: confirmed harms need authoritative results, not caller mismatch alone;
counts come from records; remediation is review-only."""

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from gauntlet.application.recall import AuditReport, EventAuditUseCase, InvalidAuditRequestError
from gauntlet.contracts import (
    AuditSummary,
    HistoricalDecision,
    RecallTrigger,
    RemediationProposal,
    ToolEvent,
)
from gauntlet.domain import RecallClassification
from gauntlet.ports import AuditFacts

T = datetime(2026, 10, 5, 10, 0, tzinfo=UTC)
NOW = datetime(2026, 10, 14, 16, 0, tzinfo=UTC)


def event(event_id: str, actor: str, outcome: str = "succeeded", minutes: int = 0) -> ToolEvent:
    return ToolEvent.model_validate(
        {"event_id": event_id, "decision_id": None, "target_id": "cartwheel-fixture",
         "tool_name": "start_refund", "actor_ref": actor, "arguments_hash": "6a" * 32,
         "occurred_at": T + timedelta(minutes=minutes), "outcome": outcome}
    )  # fmt: skip


OWNER_REFUND = event("tool-ev-001", "synthetic-owner-01")
STOLEN_REFUND = event("tool-ev-002", "synthetic-attacker-01", minutes=5)
MISMATCH_NO_MONEY = event("tool-ev-003", "synthetic-attacker-01", minutes=9)
UNKNOWN_OUTCOME = event("tool-ev-004", "synthetic-attacker-01", outcome="unknown", minutes=12)
FAILED_ATTEMPT = event("tool-ev-005", "synthetic-attacker-01", outcome="failed", minutes=15)

FACTS = {
    "tool-ev-001": AuditFacts(True, True, False, "owner refunded own order", ("ledger-tx-7701",)),
    "tool-ev-002": AuditFacts(
        True, True, True, "ledger credit went to a non-owner account", ("ledger-tx-7781",)
    ),
    # Caller ≠ owner, but the ledger has no transaction: mismatch alone, not a violation.
    "tool-ev-003": AuditFacts(
        True,
        False,
        False,
        "caller differs from owner; no ledger record found",
        limitations=("authoritative ledger not checked for this event",),
    ),  # fmt: skip
    "tool-ev-004": AuditFacts(True, True, True, "provider claims an effect"),
    "tool-ev-005": AuditFacts(True, True, True, "provider claims an effect"),
}


class History:
    def __init__(self, events: Sequence[ToolEvent]) -> None:
        self.events = tuple(events)

    async def get_decision(self, decision_id: str) -> HistoricalDecision | None:
        return None

    async def tool_events(
        self, target_id: str, tool_name: str, start_at: datetime, end_at: datetime
    ) -> Sequence[ToolEvent]:
        return [
            e for e in self.events
            if e.target_id == target_id and e.tool_name == tool_name
            and start_at <= e.occurred_at <= end_at
        ]  # fmt: skip


class Evidence:
    criterion_version = "refund-authz-1.0"

    async def facts_for(self, event: ToolEvent) -> AuditFacts:
        return FACTS[event.event_id]


def trigger(mode: str = "event_audit") -> RecallTrigger:
    return RecallTrigger.model_validate(
        {"trigger_id": "t2", "kind": "finding", "reference": "finding-refund-authz",
         "mode": mode, "start_at": "2026-10-01T00:00:00Z", "end_at": "2026-10-14T00:00:00Z",
         "target_id": "cartwheel-fixture"}
    )  # fmt: skip


def audit(*events: ToolEvent) -> AuditReport:
    use_case = EventAuditUseCase(History(events), Evidence(), lambda: NOW)
    return asyncio.run(use_case.run("recall-002", trigger(), "start_refund"))


def by_event(report: AuditReport) -> dict[str | None, RecallClassification]:
    return {v.tool_event_id: v.classification for v in report.verdicts}


def test_confirmed_effect_vs_mismatch_vs_legitimate() -> None:
    report = audit(OWNER_REFUND, STOLEN_REFUND, MISMATCH_NO_MONEY)
    assert by_event(report) == {
        "tool-ev-001": RecallClassification.AUDIT_CLEAR,
        "tool-ev-002": RecallClassification.AUDIT_VIOLATION,
        "tool-ev-003": RecallClassification.INCONCLUSIVE,
    }
    summary = report.summary
    assert (summary.audited, summary.violations, summary.clear, summary.inconclusive) == (
        3,
        1,
        1,
        1,
    )


def test_unknown_or_failed_outcome_can_never_be_a_violation() -> None:
    report = audit(UNKNOWN_OUTCOME, FAILED_ATTEMPT)
    assert set(by_event(report).values()) == {RecallClassification.INCONCLUSIVE}
    limitations = {lim for v in report.verdicts for lim in v.limitations}
    assert "tool outcome was not recorded" in limitations
    assert "effect reported for an operation not recorded as succeeded" in limitations


def test_empty_history_is_a_gap_not_clearance() -> None:
    report = audit()
    assert report.summary.audited == 0 and report.verdicts == ()
    assert "absence of logs is not clearance" in report.summary.gaps[0]


def test_remediation_is_draft_review_only() -> None:
    report = audit(OWNER_REFUND, STOLEN_REFUND, MISMATCH_NO_MONEY)
    actions = {p.action: p for p in report.proposals}
    assert set(actions) == {"reverse_transaction_review", "collect_missing_evidence"}
    reverse = actions["reverse_transaction_review"]
    assert reverse.verdict_ids == ("recall-002:tool-ev-002",)
    assert reverse.affected_actor_refs == ("synthetic-attacker-01",)
    assert all(p.status == "draft" for p in report.proposals)
    assert "synthetic-owner-01" not in {a for p in report.proposals for a in p.affected_actor_refs}


def test_verdicts_reference_tool_events_and_criterion() -> None:
    report = audit(STOLEN_REFUND)
    verdict = report.verdicts[0]
    assert verdict.mode == "event_audit" and verdict.tool_event_id == "tool-ev-002"
    assert verdict.criterion_version == "refund-authz-1.0"
    assert verdict.evidence_ids == ("ledger-tx-7781",)


def test_counterfactual_trigger_is_refused() -> None:
    use_case = EventAuditUseCase(History(()), Evidence(), lambda: NOW)
    with pytest.raises(InvalidAuditRequestError):
        asyncio.run(use_case.run("r", trigger(mode="decision_counterfactual"), "start_refund"))


def test_summary_counts_must_add_up_and_no_executed_status() -> None:
    with pytest.raises(ValidationError):
        AuditSummary.model_validate(
            {"recall_id": "r", "tool_name": "t", "start_at": T, "end_at": NOW,
             "audited": 3, "violations": 3, "clear": 1, "inconclusive": 0}
        )  # fmt: skip
    with pytest.raises(ValidationError):
        RemediationProposal.model_validate(
            {"proposal_id": "p", "recall_id": "r", "action": "reverse_transaction_review",
             "verdict_ids": ["v"], "rationale": "x", "status": "executed", "created_at": NOW}
        )  # fmt: skip
