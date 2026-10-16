"""Recall end to end: trigger -> lineage exposure -> readiness -> pinned control + counterfactual
-> materiality verdicts, plus the deterministic event audit of the tool's recorded operations.

Every verdict comes from the existing pure policies. Remediation output is a review-queue
draft only; nothing is reversed, refunded or sent.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from gauntlet.contracts import (
    ExposureRecord,
    NodeRef,
    RecallTrigger,
    RecallVerdict,
    RemediationAction,
    RemediationProposal,
)
from gauntlet.domain import RecallClassification
from gauntlet.ports import HistoricalEventStore, LineageStore

from .counterfactual import CounterfactualUseCase
from .event_audit import AuditReport, EventAuditUseCase
from .readiness import assess_readiness
from .scope import RecallScoper

_REVIEW: Final[tuple[tuple[RecallClassification, RemediationAction, str], ...]] = (
    (
        RecallClassification.TAINTED,
        "customer_contact_review",
        "The suspect source materially changed these decisions; a human reviews each case",
    ),
    (
        RecallClassification.INCONCLUSIVE,
        "collect_missing_evidence",
        "Replays could not establish the outcome; collect evidence before deciding",
    ),
    (
        RecallClassification.NOT_REPLAYABLE,
        "collect_missing_evidence",
        "Critical inputs were not recorded; exposed but undetermined, never cleared",
    ),
)


@dataclass(frozen=True)
class DecisionFinding:
    exposure: ExposureRecord
    verdict: RecallVerdict


@dataclass(frozen=True)
class RecallReport:
    recall_id: str
    trigger: RecallTrigger
    decisions: tuple[DecisionFinding, ...]
    gaps: tuple[str, ...]
    audit: AuditReport | None
    proposals: tuple[RemediationProposal, ...]

    def counts(self) -> dict[str, int]:
        result = {c.value: 0 for c in RecallClassification}
        for item in self.decisions:
            result[item.verdict.classification.value] += 1
        return result


@dataclass(frozen=True)
class RecallDependencies:
    lineage: LineageStore
    history: HistoricalEventStore
    scoper: RecallScoper
    counterfactual: CounterfactualUseCase
    audit: EventAuditUseCase
    clock: Callable[[], datetime]


class RunRecallUseCase:
    def __init__(self, deps: RecallDependencies) -> None:
        self._deps = deps

    async def execute(
        self,
        recall_id: str,
        trigger: RecallTrigger,
        *,
        audit_tool: str | None = None,
    ) -> RecallReport:
        """Counterfactual analysis of every exposed decision; optional tool event audit."""
        scope = await self._deps.scoper.trace(recall_id, trigger)
        findings: list[DecisionFinding] = []
        gaps = list(scope.gaps)
        for exposure in scope.exposures:
            decision = await self._deps.history.get_decision(exposure.decision_id)
            if decision is None:
                gaps.append(f"decision {exposure.decision_id} disappeared during analysis")
                continue
            incoming = await self._deps.lineage.edges_to(
                NodeRef(kind="decision", node_id=decision.decision_id)
            )
            # No hindsight: lineage recorded after the incident window is ignored.
            readiness = assess_readiness(
                decision, [e for e in incoming if e.recorded_at <= trigger.end_at]
            )
            verdict = await self._deps.counterfactual.evaluate(
                recall_id, exposure, decision, readiness
            )
            findings.append(DecisionFinding(exposure, verdict))
        audit = None
        if audit_tool is not None:
            audit_trigger = trigger.model_copy(update={"mode": "event_audit"})
            audit = await self._deps.audit.run(f"{recall_id}-audit", audit_trigger, audit_tool)
        return RecallReport(
            recall_id=recall_id,
            trigger=trigger,
            decisions=tuple(findings),
            gaps=tuple(dict.fromkeys(gaps)),
            audit=audit,
            proposals=self._proposals(recall_id, findings),
        )

    def _proposals(
        self, recall_id: str, findings: list[DecisionFinding]
    ) -> tuple[RemediationProposal, ...]:
        now = self._deps.clock()
        grouped: dict[RemediationAction, tuple[str, list[RecallVerdict]]] = {}
        for classification, action, rationale in _REVIEW:
            selected = [f.verdict for f in findings if f.verdict.classification is classification]
            if selected:
                _, existing = grouped.setdefault(action, (rationale, []))
                existing.extend(selected)
        return tuple(
            RemediationProposal(
                proposal_id=f"{recall_id}:{action}",
                recall_id=recall_id,
                action=action,
                verdict_ids=tuple(v.verdict_id for v in verdicts),
                rationale=rationale,
                created_at=now,
            )
            for action, (rationale, verdicts) in grouped.items()
        )
