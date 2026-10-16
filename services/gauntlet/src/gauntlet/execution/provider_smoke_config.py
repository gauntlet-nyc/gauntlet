"""Validate B-01 smoke inputs locally before creating paid resources."""

import json
from collections.abc import Mapping
from pathlib import Path

from gauntlet.contracts import ChangeRequest
from gauntlet.integrations.daytona.provider import RegisteredSnapshot, RegisteredTarget

_REGISTRATION_FIELDS = frozenset(RegisteredTarget.__dataclass_fields__)
_SNAPSHOT_FIELDS = frozenset(RegisteredSnapshot.__dataclass_fields__)
_REQUIRED_ENV = (
    "DAYTONA_API_KEY",
    "DAYTONA_API_URL",
    "DAYTONA_TARGET",
    "ANCHOR_API_KEY",
)
_ANCHOR_PROXY_ENV = ("ANCHOR_PROXY_SERVER", "ANCHOR_PROXY_USERNAME", "ANCHOR_PROXY_PASSWORD")


def preflight(
    environment: Mapping[str, str], *, spend_authorized: bool, registration_present: bool
) -> dict[str, object]:
    """Return names of missing prerequisites without returning credential values."""
    missing: list[str] = []
    if environment.get("RUN_LIVE_INTEGRATIONS") != "1":
        missing.append("live_opt_in")
    if not spend_authorized:
        missing.append("spend_authorization")
    if not registration_present:
        missing.append("registration")
    if "cartwheel-fixture" not in {
        item.strip() for item in environment.get("GAUNTLET_ALLOWED_TARGET_IDS", "").split(",")
    }:
        missing.append("cartwheel_target_allowlist")
    require_proxy = environment.get("GAUNTLET_ANCHOR_REQUIRE_PROXY", "1").strip() != "0"
    for key in _REQUIRED_ENV + (_ANCHOR_PROXY_ENV if require_proxy else ()):
        value = environment.get(key, "").strip()
        if not value or value.upper().startswith("REPLACE_"):
            missing.append(key)
    return {
        "scope": "local_prerequisites_only",
        "status": "not_tested",
        "missing": missing,
        "anchor_egress_isolation": "custom_proxy" if require_proxy else "none_weaker_isolation",
    }


def load_registration(
    path: Path, manifest: Mapping[str, object]
) -> tuple[ChangeRequest, RegisteredTarget]:
    """Bind operator snapshot registration to the committed synthetic manifest."""
    if (
        manifest.get("synthetic_only") is not True
        or manifest.get("target_id") != "cartwheel-fixture"
    ):
        raise ValueError("provider smoke requires the synthetic Cartwheel manifest")
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict) or set(raw) != _REGISTRATION_FIELDS:
        raise ValueError("registration fields differ from the expected set")
    entries = raw["snapshots"]
    if not isinstance(entries, list) or not entries:
        raise ValueError("registration snapshots must be a nonempty list")
    snapshots: list[RegisteredSnapshot] = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != _SNAPSHOT_FIELDS:
            raise ValueError("snapshot fields differ from the expected set")
        snapshots.append(RegisteredSnapshot(**entry))
    target = RegisteredTarget(**{**raw, "snapshots": tuple(snapshots)})
    if target.ready_path != "/checkout":
        raise ValueError("provider smoke requires the fixed checkout path")
    refs = manifest.get("git_refs")
    if not isinstance(refs, dict):
        raise ValueError("manifest lacks base/head revisions")
    base_sha, head_sha = refs.get("base_sha"), refs.get("head_sha")
    if (
        target.target_id != manifest.get("target_id")
        or target.fixture_id != manifest.get("fixture_id")
        or target.fixture_checksum != manifest.get("fixture_checksum_sha256")
        or not isinstance(base_sha, str)
        or not isinstance(head_sha, str)
        or base_sha == head_sha
        or {item.source_sha for item in target.snapshots} != {base_sha, head_sha}
    ):
        raise ValueError("registration does not match manifest base/head revisions and fixture")
    change = ChangeRequest(
        repository_id="cartwheel",
        base_sha=base_sha,
        head_sha=head_sha,
        fixture_id=target.fixture_id,
        target_id=target.target_id,
        max_cost_usd_cents=500,
        feature_intent="Synthetic provider connectivity smoke",
    )
    return change, target
