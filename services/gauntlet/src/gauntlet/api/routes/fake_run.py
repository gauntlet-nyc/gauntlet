"""Phase 0 fake run: serves A's frozen UI plan golden. No worker, sandbox or provider is called."""

import html
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from gauntlet.contracts import AttackSpec, RunEvent

router = APIRouter()

GOLDEN_DIR = Path(__file__).resolve().parents[6] / "docs/contracts/examples"


class FakeRunResponse(BaseModel):
    label: str
    run_id: str
    plan: AttackSpec
    events: tuple[RunEvent, ...]


def load_fake_run() -> FakeRunResponse:
    try:
        plan = AttackSpec.model_validate_json((GOLDEN_DIR / "ui-plan.v1.json").read_bytes())
        event = RunEvent.model_validate_json((GOLDEN_DIR / "run-event.v1.json").read_bytes())
    except OSError as exc:
        raise HTTPException(status_code=503, detail="frozen golden not found") from exc
    return FakeRunResponse(
        label="FAKE RUN: golden plan and event only, nothing was executed",
        run_id=event.run_id,
        plan=plan,
        events=(event,),
    )


@router.get("/runs/fake")
async def fake_run() -> FakeRunResponse:
    return load_fake_run()


@router.get("/fake-run", response_class=HTMLResponse)
async def fake_run_page() -> str:
    run = load_fake_run()
    skip = {"schema_version", "action"}
    steps = "".join(
        f"<li>{html.escape(s.action)} "
        f"{html.escape(json.dumps(s.model_dump(mode='json', exclude=skip)))}</li>"
        for s in run.plan.steps
    )
    events = "".join(
        f"<li>#{e.sequence} {html.escape(e.event_type)} by {html.escape(e.actor)}</li>"
        for e in run.events
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>Gauntlet fake run</title></head>"
        f"<body><h1>{html.escape(run.label)}</h1>"
        f"<p>Run {html.escape(run.run_id)}, attack {html.escape(run.plan.attack_id)}</p>"
        f"<p>{html.escape(run.plan.hypothesis)}</p>"
        f"<h2>Planned steps</h2><ol>{steps}</ol><h2>Events</h2><ul>{events}</ul></body></html>"
    )
