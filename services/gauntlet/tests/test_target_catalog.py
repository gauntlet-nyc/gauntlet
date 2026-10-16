"""The production target catalog comes from the reviewed synthetic Cartwheel manifest."""

import asyncio
import json
from pathlib import Path

import pytest

from gauntlet.application.gate import StaticTargetCatalog, profile_from_manifest

MANIFEST = Path(__file__).resolve().parents[3] / "apps/cartwheel/fixture-manifest.v1.json"


def test_cartwheel_manifest_becomes_the_only_authorized_target() -> None:
    profile = profile_from_manifest(json.loads(MANIFEST.read_text()))
    catalog = StaticTargetCatalog(profile)
    assert asyncio.run(catalog.get("cartwheel-fixture")) == profile
    assert asyncio.run(catalog.get("other-target")) is None
    assert profile.fixture_ids == frozenset({"baseline-v1"})
    assert profile.allows_route("/checkout")
    assert not profile.allows_route("/admin")
    assert "support-agent" in profile.agent_ids
    assert "support-agent" not in profile.synthetic_actor_ids


def test_non_synthetic_or_routeless_manifests_are_refused() -> None:
    manifest = json.loads(MANIFEST.read_text())
    with pytest.raises(ValueError):
        profile_from_manifest({**manifest, "synthetic_only": False})
    with pytest.raises(ValueError):
        profile_from_manifest({**manifest, "routes": []})
    with pytest.raises(ValueError):
        StaticTargetCatalog(profile_from_manifest(manifest), profile_from_manifest(manifest))
