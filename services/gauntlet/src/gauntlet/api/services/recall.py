"""Recall views over Session 1's RunRecallUseCase (gauntlet.composition.build_recall).

The seeded history is read through checksum-verified read-only adapters; the replay uses the
deterministic synthetic agent policy unless a live model provider is configured. Labels from
the runtime become provenance so the UI can show OFFLINE / live NOT RUN.
"""

import hashlib
import json
from datetime import datetime
from typing import Any

from gauntlet.composition import RecallRuntime
from gauntlet.contracts import RecallTrigger
from gauntlet.domain import RecallClassification

from ..schemas import (
    AuditView,
    CounterfactualCase,
    CounterfactualView,
    DecisionView,
    Provenance,
    ReviewItem,
)

CF_RECALL_ID = "recall-kb-117"
TOOL = "request_refund"

_LABEL_TEXT = {
    "seeded_synthetic_files": "OFFLINE: seeded synthetic history from apps/cartwheel/history; "
    "SurrealDB live NOT RUN",
    "seeded_ledger": "OFFLINE: authoritative state is the synthetic ledger/orders fixture",
    "offline_captured_agent_replay": "OFFLINE captured-input replay with the deterministic "
    "synthetic agent policy (no model call); Daytona replay world live NOT RUN",
}


def canonical_sha256(document: object) -> str:
    text = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode()).hexdigest()


def _provenance(labels: dict[str, str]) -> list[Provenance]:
    out = []
    for part, label in labels.items():
        live = label.startswith("live_")
        out.append(
            Provenance(
                provider=f"{part}:{label}",
                mode="live" if live else "offline_fixture",
                live=live,
                label=_LABEL_TEXT.get(label, label),
            )
        )
    return out


class RecallService:
    def __init__(self, runtime: RecallRuntime) -> None:
        self._runtime = runtime
        self._archive = runtime.archive
        self._audit: AuditView | None = None
        self._cf: CounterfactualView | None = None

    @property
    def uses_live_provider(self) -> bool:
        """Use the composed runtime, not mutable environment settings, for authorization."""
        return any(label.startswith("live_") for label in self._runtime.labels.values())

    @property
    def window(self) -> tuple[datetime, datetime]:
        start = datetime.fromisoformat(self._archive.manifest["window_start"])
        end = datetime.fromisoformat(self._archive.manifest["window_end"])
        return start, end

    def _trigger(self, reference: str) -> RecallTrigger:
        start, end = self.window
        return RecallTrigger.model_validate(
            {
                "trigger_id": f"trig-{reference}",
                "kind": "document",
                "reference": reference,
                "mode": "decision_counterfactual",
                "start_at": start,
                "end_at": end,
                "target_id": self._archive.manifest["target_id"],
            }
        )

    def timeline(self) -> list[DecisionView]:
        by_decision: dict[str, list[Any]] = {}
        for event in self._archive.tool_events:
            if event.decision_id:
                by_decision.setdefault(event.decision_id, []).append(event)
        views = []
        for d in sorted(self._archive.decisions.values(), key=lambda d: d.occurred_at):
            message = self._archive.messages.get(d.decision_id, {})
            views.append(
                DecisionView(
                    decision=d,
                    tool_events=by_decision.get(d.decision_id, []),
                    requester=message.get("actor_ref", d.actor_ref),
                    message=message.get("text", ""),
                )
            )
        return views

    async def _run(self, reference: str) -> None:
        report = await self._runtime.use_case.execute(
            CF_RECALL_ID if reference == "kb-117" else f"recall-{reference}",
            self._trigger(reference),
            audit_tool=TOOL,
        )
        provenance = _provenance(self._runtime.labels)
        cases = []
        for item in report.decisions:
            decision = self._archive.decisions[item.exposure.decision_id]
            cases.append(
                CounterfactualCase(
                    decision_id=decision.decision_id,
                    exposure=item.exposure,
                    replayable=item.verdict.classification
                    is not RecallClassification.NOT_REPLAYABLE,
                    missing_fields=[m.field for m in decision.missing_inputs if m.critical],
                    verdict=item.verdict,
                )
            )
        self._cf = CounterfactualView(
            recall_id=report.recall_id,
            trigger_reference=reference,
            cases=cases,
            gaps=list(report.gaps),
            counts=report.counts(),
            proposals=list(report.proposals),
            provenance=provenance,
        )
        if report.audit is not None and self._audit is None:
            audit = report.audit
            self._audit = AuditView(
                recall_id=audit.summary.recall_id,
                summary=audit.summary,
                verdicts=list(audit.verdicts),
                proposals=list(audit.proposals),
                provenance=[p for p in provenance if not p.provider.startswith("replay:")],
            )

    async def audit(self) -> AuditView:
        if self._audit is None:
            await self._run("kb-117")
        if self._audit is None:
            raise RuntimeError("event audit did not run")
        return self._audit

    async def counterfactual(self, reference: str = "kb-117") -> CounterfactualView:
        if self._cf is None or self._cf.trigger_reference != reference:
            await self._run(reference)
        if self._cf is None:
            raise RuntimeError("counterfactual did not run")
        return self._cf

    async def review_queue(self, approvals: dict[str, tuple[str, str, str]]) -> list[ReviewItem]:
        """Human review items. Every action is review-only; nothing is reversed or sent."""
        audit = await self.audit()
        cf = await self.counterfactual("kb-117")
        items: list[ReviewItem] = []
        for proposal in [*audit.proposals, *cf.proposals]:
            items.append(
                self._item(
                    proposal.proposal_id,
                    "remediation_proposal",
                    proposal.recall_id,
                    f"{proposal.action} — {len(proposal.verdict_ids)} items",
                    proposal.rationale,
                    proposal.action,
                    proposal.model_dump(mode="json", exclude={"created_at", "status"}),
                    approvals,
                )
            )
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
