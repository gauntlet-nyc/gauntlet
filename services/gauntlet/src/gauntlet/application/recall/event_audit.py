"""Recall `event_audit`: classify recorded tool operations against authoritative state.

Deterministic, no model. A caller/owner mismatch alone is never a violation: the evidence
provider must confirm the forbidden *result* from authoritative records, with complete logs.
Every case lands in a review queue as a draft; nothing is executed.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from gauntlet.contracts import (
    AuditSummary,
    RecallTrigger,
    RecallVerdict,
    RemediationAction,
    RemediationProposal,
    ToolEvent,
)
from gauntlet.domain import AuditEvidence, RecallClassification, classify_event_audit
from gauntlet.ports import AuditEvidenceProvider, AuditFacts, HistoricalEventStore

from ..errors import ApplicationError

_QUEUE: Final[tuple[tuple[RecallClassification, RemediationAction, str], ...]] = (
    (
        RecallClassification.AUDIT_VIOLATION,
        "reverse_transaction_review",
        "Confirmed forbidden effects; a human decides on reversal and customer contact",
    ),
    (
        RecallClassification.INCONCLUSIVE,
        "collect_missing_evidence",
        "Evidence was insufficient to clear or confirm; collect records before deciding",
    ),
)


class InvalidAuditRequestError(ApplicationError):
    """The trigger is not an event-audit trigger."""


@dataclass(frozen=True)
class AuditReport:
    summary: AuditSummary
    verdicts: tuple[RecallVerdict, ...]
    proposals: tuple[RemediationProposal, ...]


def _effective_evidence(event: ToolEvent, facts: AuditFacts) -> tuple[AuditEvidence, list[str]]:
    limitations = list(facts.limitations)
    logs_complete = facts.relevant_logs_complete
    effect = facts.forbidden_effect_confirmed
    if event.outcome == "unknown":
        logs_complete = False
        limitations.append("tool outcome was not recorded")
    if effect and event.outcome != "succeeded":
        effect = False
        logs_complete = False
        limitations.append("effect reported for an operation not recorded as succeeded")
    return AuditEvidence(logs_complete, facts.authoritative_state_checked, effect), limitations


class EventAuditUseCase:
    def __init__(
        self,
        history: HistoricalEventStore,
        evidence: AuditEvidenceProvider,
        clock: Callable[[], datetime],
    ) -> None:
        self._history = history
        self._evidence = evidence
        self._clock = clock

    async def run(self, recall_id: str, trigger: RecallTrigger, tool_name: str) -> AuditReport:
        if trigger.mode != "event_audit":
            raise InvalidAuditRequestError("trigger mode must be event_audit")
        events = await self._history.tool_events(
            trigger.target_id, tool_name, trigger.start_at, trigger.end_at
        )
        gaps: list[str] = []
        if not events:
            gaps.append("no recorded operations in the window; absence of logs is not clearance")
        verdicts = [await self._classify(recall_id, event) for event in events]
        counts = {c: sum(v.classification is c for v in verdicts) for c in RecallClassification}
        summary = AuditSummary(
            recall_id=recall_id,
            tool_name=tool_name,
            start_at=trigger.start_at,
            end_at=trigger.end_at,
            audited=len(verdicts),
            violations=counts[RecallClassification.AUDIT_VIOLATION],
            clear=counts[RecallClassification.AUDIT_CLEAR],
            inconclusive=counts[RecallClassification.INCONCLUSIVE],
            gaps=tuple(gaps),
        )
        return AuditReport(summary, tuple(verdicts), self._proposals(recall_id, events, verdicts))

    async def _classify(self, recall_id: str, event: ToolEvent) -> RecallVerdict:
        facts = await self._evidence.facts_for(event)
        evidence, limitations = _effective_evidence(event, facts)
        classification = classify_event_audit(evidence)
        return RecallVerdict(
            verdict_id=f"{recall_id}:{event.event_id}",
            recall_id=recall_id,
            decision_id=event.decision_id,
            tool_event_id=event.event_id,
            mode="event_audit",
            classification=classification,
            rationale=facts.rationale,
            criterion_version=self._evidence.criterion_version,
            evidence_ids=facts.evidence_ids,
            limitations=tuple(limitations),
        )

    def _proposals(
        self, recall_id: str, events: Sequence[ToolEvent], verdicts: Sequence[RecallVerdict]
    ) -> tuple[RemediationProposal, ...]:
        actors = {e.event_id: e.actor_ref for e in events}
        now = self._clock()
        proposals: list[RemediationProposal] = []
        for classification, action, rationale in _QUEUE:
            selected = [v for v in verdicts if v.classification is classification]
            if not selected:
                continue
            proposals.append(
                RemediationProposal(
                    proposal_id=f"{recall_id}:{action}",
                    recall_id=recall_id,
                    action=action,
                    verdict_ids=tuple(v.verdict_id for v in selected),
                    affected_actor_refs=tuple(
                        sorted({actors[v.tool_event_id] for v in selected if v.tool_event_id})
                    ),
                    rationale=rationale,
                    evidence_ids=tuple(e for v in selected for e in v.evidence_ids),
                    created_at=now,
                )
            )
        return tuple(proposals)
