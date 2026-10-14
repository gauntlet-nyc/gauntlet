"""Human review of fix plans. Recording a decision never executes or merges anything."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from gauntlet.application import StaleApprovalError
from gauntlet.application.gate import ApprovalScope, ApprovalService
from gauntlet.application.gate.approvals import fix_plan_hash
from gauntlet.contracts import ApprovalDecision, ApprovalRecord, FixPlan
from gauntlet.ports.errors import DuplicateApprovalError

from ..auth import Reviewer
from ..dev_stores import DevState

router = APIRouter(prefix="/v1/fix-plans")


def dev_state(request: Request) -> DevState:
    state: DevState = request.app.state.dev
    return state


State = Annotated[DevState, Depends(dev_state)]


class FixPlanView(BaseModel):
    label: str
    fix_plan: FixPlan
    plan_sha256: str
    target_id: str
    fixture_id: str
    approvals: tuple[ApprovalRecord, ...]


def _view(state: DevState, fix_plan_id: str) -> FixPlanView:
    stored = state.fix_plans.get(fix_plan_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="unknown fix plan")
    return FixPlanView(
        label="DEMO fix plan from the golden file; approving records a decision only",
        fix_plan=stored.plan,
        plan_sha256=fix_plan_hash(stored.plan),
        target_id=stored.target_id,
        fixture_id=stored.fixture_id,
        approvals=state.approvals.for_subject(fix_plan_id),
    )


@router.get("/{fix_plan_id}")
async def get_fix_plan(fix_plan_id: str, state: State) -> FixPlanView:
    return _view(state, fix_plan_id)


@router.post("/{fix_plan_id}/approve")
async def decide_fix_plan(
    fix_plan_id: str, decision: ApprovalDecision, reviewer: Reviewer, state: State
) -> ApprovalRecord:
    stored = state.fix_plans.get(fix_plan_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="unknown fix plan")
    if decision.subject != "fix_plan" or decision.subject_id != fix_plan_id:
        raise HTTPException(status_code=422, detail="decision does not match this fix plan")
    service = ApprovalService(
        state.approvals, lambda: datetime.now(UTC), lambda: f"apr-{uuid4().hex[:16]}"
    )
    scope = ApprovalScope(
        run_id=stored.plan.run_id,
        target_id=stored.target_id,
        fixture_id=stored.fixture_id,
        current_plan_sha256=fix_plan_hash(stored.plan),
        allowed_paths=tuple(stored.plan.allowed_paths),
    )
    try:
        return await service.record(scope, decision, reviewer)
    except StaleApprovalError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DuplicateApprovalError as exc:
        raise HTTPException(status_code=409, detail="approval id collision, retry") from exc
