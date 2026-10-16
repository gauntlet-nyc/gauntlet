"""Gate runs: start, list, get (diff, plan, attempts, verdict, fix plan, events, briefing)."""

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Response

from gauntlet.application.errors import ApprovalDeniedError
from gauntlet.application.voice import build_briefing
from gauntlet.intake.github import render_check_run
from gauntlet.settings import Settings

from ..auth import Reviewer, authenticated_reviewer
from ..container import get_container
from ..schemas import (
    BriefingView,
    ChangeOption,
    CheckRunPreview,
    GateRunSummary,
    GateRunView,
    Provenance,
    StartGateRun,
)

router = APIRouter(prefix="/gate", tags=["gate"])

TEMPLATED_BRIEFING = Provenance(
    provider="templated-briefing",
    mode="offline_fixture",
    live=False,
    label="Briefing text is templated from persisted findings; ElevenLabs voice live NOT RUN",
)


@router.get("/changes")
async def list_changes() -> list[ChangeOption]:
    return get_container().gate.changes()


@router.post("/runs", status_code=201)
async def start_gate_run(
    body: StartGateRun, authorization: Annotated[str | None, Header()] = None
) -> GateRunView:
    """Offline runs are open. A run that would call a live, paid provider needs a reviewer."""
    service = get_container().gate
    if service.uses_live_provider(Settings.from_env(), body.change_id):
        authenticated_reviewer(authorization)  # raises 401 without a valid reviewer token
    return await service.start(body.change_id)


@router.get("/runs")
async def list_gate_runs() -> list[GateRunSummary]:
    return get_container().gate.summaries()


def _run(run_id: str) -> GateRunView:
    record = get_container().gate.runs.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="unknown run")
    return record.view


@router.get("/runs/{run_id}")
async def get_gate_run(run_id: str) -> GateRunView:
    return _run(run_id)


@router.get("/runs/{run_id}/briefing")
async def get_gate_briefing(run_id: str) -> BriefingView:
    view = _run(run_id)
    gaps = 1 if view.status == "not_tested" else 0
    sequence = view.events[-1].sequence if view.events else 0
    briefing = build_briefing(view.run_id, view.findings, gaps, sequence)
    return BriefingView(briefing=briefing, audio_available=False, provenance=TEMPLATED_BRIEFING)


@router.get(
    "/runs/{run_id}/artifacts/{artifact_id}",
    response_class=Response,
    responses={200: {"content": {"image/png": {}, "application/json": {}}}},
)
async def get_gate_artifact(run_id: str, artifact_id: str) -> Response:
    """Serves stored evidence bytes only by exact run and artifact ID."""
    record = get_container().gate.runs.get(run_id)
    stored = record.artifacts.get(artifact_id) if record else None
    if stored is None:
        raise HTTPException(status_code=404, detail="unknown artifact")
    media_type, content = stored
    return Response(
        content=content,
        media_type=media_type,
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
    )


@router.get("/runs/{run_id}/check-run")
async def get_gate_check_run(run_id: str) -> CheckRunPreview:
    """Preview of the GitHub check run (checks-only; never comments, approves or merges)."""
    view = _run(run_id)
    report = render_check_run(view.run_id, view.findings, [], view.not_tested_reason)
    return CheckRunPreview(
        name=report.name,
        conclusion=report.conclusion,
        title=report.title,
        summary=report.summary,
        details_url=report.details_url,
        published=False,
        note="Preview only: the GitHub App is not installed, so nothing was published.",
    )


@router.post("/runs/{run_id}/repair")
async def run_gate_repair(run_id: str, reviewer: Reviewer) -> GateRunView:
    """Apply the human-approved fix plan in a fresh worktree and re-verify it.

    Needs a reviewer token and a prior approval of the exact plan hash (single use). The
    result is review-only: nothing is merged, pushed or deployed.
    """
    service = get_container().gate
    if run_id not in service.runs:
        raise HTTPException(status_code=404, detail="unknown run")
    service.append_event(run_id, "repair_requested", {"reviewer_id": reviewer.reviewer_id})
    try:
        view = await service.run_repair(run_id)
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ApprovalDeniedError as exc:
        raise HTTPException(status_code=409, detail=f"approval refused: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return view
