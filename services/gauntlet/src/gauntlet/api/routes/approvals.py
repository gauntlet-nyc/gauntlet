"""Hash-bound human approvals (A-03) with dev-grade reviewer tokens.

An approval only records a human decision. It never merges, deploys, refunds or contacts anyone;
an approved fix plan still has to pass an independent replay before anything else happens.
"""

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from gauntlet.application.errors import StaleApprovalError
from gauntlet.application.gate import ApprovalScope
from gauntlet.contracts import ApprovalDecision, ApprovalRecord

from ..auth import Reviewer
from ..container import get_container
from ..schemas import ApprovalRequest, ApprovalView

router = APIRouter(prefix="/approvals", tags=["approvals"])


def _scope(body: ApprovalRequest) -> ApprovalScope:
    container = get_container()
    if body.subject == "remediation":
        raise HTTPException(status_code=500, detail="remediation scopes are resolved async")
    record = container.gate.runs.get(body.run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="unknown run")
    view = record.view
    if body.subject == "fix_plan":
        if view.fix_plan is None or view.fix_plan.plan.fix_plan_id != body.subject_id:
            raise HTTPException(status_code=404, detail="unknown fix plan for this run")
        return ApprovalScope(
            run_id=view.run_id,
            target_id=view.target_id,
            fixture_id=view.fixture_id,
            current_plan_sha256=view.fix_plan.plan_sha256,
            allowed_paths=tuple(view.fix_plan.allowed_paths),
        )
    if not view.attacks or view.plan_sha256 is None:
        raise HTTPException(status_code=409, detail="run has no frozen plan to approve")
    if body.subject_id not in {a.attack_id for a in view.attacks}:
        raise HTTPException(status_code=404, detail="unknown attack for this run")
    return ApprovalScope(
        run_id=view.run_id,
        target_id=view.target_id,
        fixture_id=view.fixture_id,
        current_plan_sha256=view.plan_sha256,
    )


async def _remediation_scope(body: ApprovalRequest) -> ApprovalScope:
    container = get_container()
    items = await container.recall.review_queue(container.review_decisions)
    item = next((i for i in items if i.item_id == body.subject_id), None)
    if item is None or item.recall_id != body.run_id:
        raise HTTPException(status_code=404, detail="unknown review item for this recall")
    refund = container.gate.manifests["refund-tool"]
    return ApprovalScope(
        run_id=item.recall_id,
        target_id=refund["target_id"],
        fixture_id=refund["fixture_id"],
        current_plan_sha256=item.plan_sha256,
    )


@router.post("", status_code=201)
async def record_approval(body: ApprovalRequest, reviewer: Reviewer) -> ApprovalView:
    container = get_container()
    try:
        decision = ApprovalDecision(
            subject=body.subject,
            subject_id=body.subject_id,
            plan_sha256=body.plan_sha256,
            decision=body.decision,
            reason=body.reason,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=422, detail=[e["msg"] for e in exc.errors(include_url=False)]
        ) from exc
    scope = await _remediation_scope(body) if body.subject == "remediation" else _scope(body)
    try:
        record = await container.approvals.record(scope, decision, reviewer)
    except StaleApprovalError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if body.subject == "remediation":
        container.review_decisions[body.subject_id] = (
            record.approval_id,
            record.plan_sha256,
            record.decision,
        )
        note = "Recorded for human review only. Nothing was reversed, refunded or sent."
    else:
        container.gate.append_event(
            record.run_id,
            "approval_recorded",
            {
                "approval_id": record.approval_id,
                "subject": record.subject,
                "decision": record.decision,
                "plan_sha256": record.plan_sha256,
            },
        )
        note = (
            "Approval bound to this exact plan hash, single use, expires "
            f"{record.expires_at.isoformat()}. No merge or deploy happens automatically."
        )
    return ApprovalView(record=record, note=note)


@router.get("")
async def list_approvals() -> list[ApprovalRecord]:
    return get_container().approval_store.list()
