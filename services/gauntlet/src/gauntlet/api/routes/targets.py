"""Cartwheel target fixture routes. Reads the generated manifest; runs nothing."""

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from gauntlet.contracts import ChangeRequest

router = APIRouter(prefix="/targets")

MANIFEST = Path(__file__).resolve().parents[6] / "apps/cartwheel/fixture-manifest.v1.json"
DEFAULT_CHANGE = "help-button"


def _load_manifest() -> dict[str, Any]:
    try:
        manifest: dict[str, Any] = json.loads(MANIFEST.read_text())
    except OSError as exc:
        raise HTTPException(status_code=503, detail="fixture manifest not found") from exc
    return manifest


def _change_request(change_id: str) -> ChangeRequest:
    manifest = _load_manifest()
    change = next((c for c in manifest.get("changes", []) if c["id"] == change_id), None)
    if change is None:
        raise HTTPException(status_code=404, detail="unknown change")
    if not manifest.get("base_sha") or not change.get("head_sha"):
        raise HTTPException(status_code=503, detail="fixture commits not built yet")
    return ChangeRequest(
        repository_id="cartwheel",
        base_sha=manifest["base_sha"],
        head_sha=change["head_sha"],
        fixture_id=manifest["fixture_id"],
        target_id=manifest["target_id"],
        max_cost_usd_cents=500,
        feature_intent=change["feature_intent"],
    )


@router.get("/cartwheel/change-request")
async def cartwheel_change_request() -> ChangeRequest:
    return _change_request(DEFAULT_CHANGE)


@router.get("/cartwheel/changes/{change_id}/change-request")
async def cartwheel_named_change_request(change_id: str) -> ChangeRequest:
    return _change_request(change_id)
