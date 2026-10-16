"""Recall: decision timeline, event audit, counterfactual, lineage and the human review queue."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException

from ..auth import authenticated_reviewer
from ..container import get_container
from ..schemas import AuditView, CounterfactualView, DecisionView, LineageView, ReviewItem

router = APIRouter(prefix="/recall", tags=["recall"])


def authorize_recall(authorization: Annotated[str | None, Header()] = None) -> None:
    """Replay-triggering reads require a reviewer whenever the runtime can call providers."""
    if get_container().recall.uses_live_provider:
        authenticated_reviewer(authorization)


@router.get("/timeline")
async def recall_timeline() -> list[DecisionView]:
    return get_container().recall.timeline()


@router.get("/audit", dependencies=[Depends(authorize_recall)])
async def recall_audit() -> AuditView:
    return await get_container().recall.audit()


@router.get("/counterfactual", dependencies=[Depends(authorize_recall)])
async def recall_counterfactual(trigger: str = "kb-117") -> CounterfactualView:
    if not trigger.startswith("kb-"):
        raise HTTPException(status_code=422, detail="only KB chunk triggers are seeded")
    return await get_container().recall.counterfactual(trigger)


@router.get("/lineage/{decision_id}", dependencies=[Depends(authorize_recall)])
async def recall_lineage(decision_id: str) -> LineageView:
    view = await get_container().recall.counterfactual()
    case = next((c for c in view.cases if c.decision_id == decision_id), None)
    if case is None:
        raise HTTPException(status_code=404, detail="decision is not exposed to the trigger")
    return LineageView(edges=list(case.exposure.path))


@router.get("/review-queue", dependencies=[Depends(authorize_recall)])
async def recall_review_queue() -> list[ReviewItem]:
    container = get_container()
    return await container.recall.review_queue(container.review_decisions)
