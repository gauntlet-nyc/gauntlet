"""Recall composition: real A-04/05/06 use cases over the seeded history's offline adapters."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from gauntlet.application.recall import RecallScoper, assess_readiness
from gauntlet.application.recall.counterfactual import CounterfactualUseCase
from gauntlet.application.recall.event_audit import EventAuditUseCase
from gauntlet.contracts import NodeRef, RecallTrigger
from gauntlet.domain import RecallClassification
from gauntlet.ports import ReplayWorld

from ..offline.history import FixtureHistory, FixtureLedgerEvidence, FixtureLineageStore
from ..offline.replay import LABEL as REPLAY_LABEL
from ..offline.replay import FixtureWorldResolver, SyntheticAgentReplay
from ..schemas import (
    AuditView,
    CounterfactualCase,
    CounterfactualView,
    DecisionView,
    Provenance,
    ReviewItem,
)

AUDIT_RECALL_ID = "recall-audit-refund"
CF_RECALL_ID = "recall-cf-kb-117"
TOOL = "request_refund"

HISTORY_PROVENANCE = Provenance(
    provider="cartwheel-history-fixture",
    mode="offline_fixture",
    live=False,
    label="OFFLINE: seeded synthetic history from apps/cartwheel/history; SurrealDB live NOT RUN",
)
LEDGER_PROVENANCE = Provenance(
    provider="cartwheel-synthetic-ledger",
    mode="offline_fixture",
    live=False,
    label="OFFLINE: authoritative state is the synthetic ledger/orders fixture",
)
REPLAY_PROVENANCE = Provenance(
    provider="synthetic-agent-replay",
    mode="offline_synthetic",
    live=False,
    label=f"{REPLAY_LABEL}; Daytona replay world and model live NOT RUN",
)


def canonical_sha256(document: object) -> str:
    text = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode()).hexdigest()


class RecallService:
    def __init__(self, history: FixtureHistory, world: ReplayWorld | None) -> None:
        self._h = history
        self._store = FixtureLineageStore(history)
        self._world = world
        self._audit: AuditView | None = None
        self._cf: CounterfactualView | None = None

    @property
    def window(self) -> tuple[datetime, datetime]:
        start = datetime.fromisoformat(self._h.manifest["window_start"])
        end = datetime.fromisoformat(self._h.manifest["window_end"])
        return start, end

    def _trigger(self, trigger_id: str, kind: str, reference: str, mode: str) -> RecallTrigger:
        start, end = self.window
        return RecallTrigger.model_validate(
            {
                "trigger_id": trigger_id,
                "kind": kind,
                "reference": reference,
                "mode": mode,
                "start_at": start,
                "end_at": end,
                "target_id": self._h.manifest["target_id"],
            }
        )

    def timeline(self) -> list[DecisionView]:
        by_decision: dict[str, list[Any]] = {}
        for event in self._h.tool_events:
            if event.decision_id:
                by_decision.setdefault(event.decision_id, []).append(event)
        return [
            DecisionView(
                decision=d,
                tool_events=by_decision.get(d.decision_id, []),
                requester=self._h.messages.get(d.decision_id, {}).get("actor_ref", d.actor_ref),
                message=self._h.messages.get(d.decision_id, {}).get("text", ""),
            )
            for d in sorted(self._h.decisions.values(), key=lambda d: d.occurred_at)
        ]

    async def audit(self) -> AuditView:
        if self._audit is None:
            use_case = EventAuditUseCase(
                self._store, FixtureLedgerEvidence(self._h), clock=lambda: datetime.now(UTC)
            )
            trigger = self._trigger("trig-refund-window", "tool_result_window", TOOL, "event_audit")
            report = await use_case.run(AUDIT_RECALL_ID, trigger, TOOL)
            self._audit = AuditView(
                recall_id=AUDIT_RECALL_ID,
                summary=report.summary,
                verdicts=list(report.verdicts),
                proposals=list(report.proposals),
                provenance=[HISTORY_PROVENANCE, LEDGER_PROVENANCE],
            )
        return self._audit

    async def counterfactual(self, reference: str = "kb-117") -> CounterfactualView:
        if self._cf is not None and self._cf.trigger_reference == reference:
            return self._cf
        trigger = self._trigger(
            f"trig-{reference}", "document", reference, "decision_counterfactual"
        )
        scope = await RecallScoper(self._store, self._store).trace(CF_RECALL_ID, trigger)
        use_case = CounterfactualUseCase(
            SyntheticAgentReplay(self._h), FixtureWorldResolver(self._world)
        )
        cases: list[CounterfactualCase] = []
        for exposure in scope.exposures:
            decision = self._h.decisions[exposure.decision_id]
            incoming = await self._store.edges_to(
                NodeRef(kind="decision", node_id=exposure.decision_id)
            )
            readiness = assess_readiness(decision, incoming)
            verdict = await use_case.evaluate(CF_RECALL_ID, exposure, decision, readiness)
            cases.append(
                CounterfactualCase(
                    decision_id=decision.decision_id,
                    exposure=exposure,
                    replayable=readiness.replayable,
                    missing_fields=[m.field for m in readiness.missing if m.critical],
                    verdict=verdict,
                )
            )
        counts = {c.value: 0 for c in RecallClassification}
        for case in cases:
            counts[case.verdict.classification.value] += 1
        self._cf = CounterfactualView(
            recall_id=CF_RECALL_ID,
            trigger_reference=reference,
            cases=cases,
            gaps=list(scope.gaps),
            counts=counts,
            provenance=[HISTORY_PROVENANCE, REPLAY_PROVENANCE],
        )
        return self._cf

    async def review_queue(self, approvals: dict[str, tuple[str, str, str]]) -> list[ReviewItem]:
        """Human review items. Every action is review-only; nothing is reversed or sent."""
        items: list[ReviewItem] = []
        audit = await self.audit()
        for proposal in audit.proposals:
            items.append(
                self._item(
                    proposal.proposal_id,
                    "remediation_proposal",
                    audit.recall_id,
                    f"{proposal.action} — {len(proposal.verdict_ids)} operations",
                    proposal.rationale,
                    proposal.action,
                    proposal.model_dump(mode="json", exclude={"created_at", "status"}),
                    approvals,
                )
            )
        cf = await self.counterfactual()
        for case in cf.cases:
            if case.verdict.classification in (
                RecallClassification.TAINTED,
                RecallClassification.INCONCLUSIVE,
                RecallClassification.NOT_REPLAYABLE,
            ):
                items.append(
                    self._item(
                        case.verdict.verdict_id,
                        "counterfactual_case",
                        cf.recall_id,
                        f"{case.decision_id}: {case.verdict.classification.value}",
                        case.verdict.rationale,
                        case.verdict.classification.value,
                        case.verdict.model_dump(mode="json"),
                        approvals,
                    )
                )
        return items

    @staticmethod
    def _item(
        item_id: str,
        kind: str,
        recall_id: str,
        title: str,
        rationale: str,
        classification: str,
        document: object,
        approvals: dict[str, tuple[str, str, str]],
    ) -> ReviewItem:
        plan_sha = canonical_sha256(document)
        decided = approvals.get(item_id)
        status = "pending"
        approval_id = None
        if decided and decided[1] == plan_sha:
            approval_id = decided[0]
            status = "approved_for_review" if decided[2] == "approved" else "dismissed"
        return ReviewItem(
            item_id=item_id,
            kind=kind,  # type: ignore[arg-type]
            recall_id=recall_id,
            title=title,
            rationale=rationale,
            classification=classification,
            plan_sha256=plan_sha,
            status=status,  # type: ignore[arg-type]
            approval_id=approval_id,
        )
