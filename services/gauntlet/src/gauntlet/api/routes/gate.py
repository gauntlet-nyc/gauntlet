"""Gate runs: start, list, get (diff, plan, attempts, verdict, fix plan, events, briefing)."""

from fastapi import APIRouter, HTTPException

from gauntlet.application.voice import build_briefing

from ..container import get_container
from ..schemas import (
    BriefingView,
    ChangeOption,
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
async def start_gate_run(body: StartGateRun) -> GateRunView:
    return await get_container().gate.start(body.change_id)


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
