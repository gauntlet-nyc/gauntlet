"""Recall: decision timeline, event audit, counterfactual, lineage and the human review queue."""

from fastapi import APIRouter, HTTPException

from ..container import get_container
from ..schemas import AuditView, CounterfactualView, DecisionView, LineageView, ReviewItem

router = APIRouter(prefix="/recall", tags=["recall"])


@router.get("/timeline")
async def recall_timeline() -> list[DecisionView]:
    return get_container().recall.timeline()


@router.get("/audit")
async def recall_audit() -> AuditView:
    return await get_container().recall.audit()


@router.get("/counterfactual")
async def recall_counterfactual(trigger: str = "kb-117") -> CounterfactualView:
    if not trigger.startswith("kb-"):
        raise HTTPException(status_code=422, detail="only KB chunk triggers are seeded")
    return await get_container().recall.counterfactual(trigger)


@router.get("/lineage/{decision_id}")
async def recall_lineage(decision_id: str) -> LineageView:
    view = await get_container().recall.counterfactual()
    case = next((c for c in view.cases if c.decision_id == decision_id), None)
    if case is None:
        raise HTTPException(status_code=404, detail="decision is not exposed to the trigger")
    return LineageView(edges=list(case.exposure.path))


@router.get("/review-queue")
async def recall_review_queue() -> list[ReviewItem]:
    container = get_container()
    return await container.recall.review_queue(container.review_decisions)
