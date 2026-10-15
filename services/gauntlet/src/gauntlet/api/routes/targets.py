"""Cartwheel target fixture routes. Reads the generated manifest; runs nothing."""

import json
from importlib import resources

from fastapi import APIRouter, HTTPException

from gauntlet.contracts import ChangeRequest

router = APIRouter(prefix="/targets")

MANIFEST = resources.files("gauntlet.api").joinpath(
    "fixtures", "cartwheel-fixture-manifest.v1.json"
)
FEATURE_INTENT = "Add a floating Help button"


@router.get("/cartwheel/change-request")
async def cartwheel_change_request() -> ChangeRequest:
    try:
        manifest = json.loads(MANIFEST.read_text())
    except OSError as exc:
        raise HTTPException(status_code=503, detail="fixture manifest not found") from exc
    refs = manifest["git_refs"]
    if not refs["base_sha"] or not refs["head_sha"]:
        raise HTTPException(status_code=503, detail="fixture commits not built yet")
    return ChangeRequest(
        repository_id="cartwheel",
        base_sha=refs["base_sha"],
        head_sha=refs["head_sha"],
        fixture_id=manifest["fixture_id"],
        target_id=manifest["target_id"],
        max_cost_usd_cents=500,
        feature_intent=FEATURE_INTENT,
    )
