"""The B-01 live entry point refuses incomplete setup before provider calls."""

import json
from pathlib import Path

import pytest

from gauntlet.execution.provider_smoke_config import load_registration, preflight

BASE = "a" * 40
HEAD = "b" * 40
CHECKSUM = "c" * 64


def manifest() -> dict[str, object]:
    return {
        "target_id": "cartwheel-fixture",
        "fixture_id": "baseline-v1",
        "fixture_checksum_sha256": CHECKSUM,
        "synthetic_only": True,
        "git_refs": {"base_sha": BASE, "head_sha": HEAD},
    }


def registration() -> dict[str, object]:
    return {
        "target_id": "cartwheel-fixture",
        "fixture_id": "baseline-v1",
        "fixture_checksum": CHECKSUM,
        "fixture_state_digest": "d" * 64,
        "fixture_state_path": "/workspace/cartwheel/fixture-state.json",
        "repo_path": "/workspace/cartwheel",
        "preview_port": 3100,
        "preview_domain_suffix": ".proxy.daytona.work",
        "ready_path": "/checkout",
        "snapshots": [
            {"source_sha": BASE, "snapshot": "base-snapshot", "image_digest": "e" * 64},
            {"source_sha": HEAD, "snapshot": "head-snapshot", "image_digest": "e" * 64},
        ],
    }


def test_preflight_reports_missing_inputs_without_exposing_secret_values() -> None:
    result = preflight(
        {
            "RUN_LIVE_INTEGRATIONS": "1",
            "DAYTONA_API_KEY": "real-daytona-secret",
            "ANCHOR_API_KEY": "real-anchor-secret",
        },
        spend_authorized=False,
        registration_present=False,
    )
    assert result["status"] == "not_tested"
    assert "spend_authorization" in result["missing"]
    assert "registration" in result["missing"]
    assert "real-daytona-secret" not in json.dumps(result)
    assert "real-anchor-secret" not in json.dumps(result)


def test_registration_must_match_manifest_revisions_and_checksum(tmp_path: Path) -> None:
    path = tmp_path / "registered.json"
    path.write_text(json.dumps(registration()))
    change, target = load_registration(path, manifest())
    assert change.base_sha == BASE and change.head_sha == HEAD
    assert target.fixture_checksum == CHECKSUM
    mismatched = registration()
    mismatched["snapshots"] = [
        {"source_sha": BASE, "snapshot": "base-snapshot", "image_digest": "e" * 64}
    ]
    path.write_text(json.dumps(mismatched))
    with pytest.raises(ValueError, match="base/head revisions"):
        load_registration(path, manifest())


def test_registration_rejects_unexpected_fields(tmp_path: Path) -> None:
    path = tmp_path / "registered.json"
    path.write_text(json.dumps({**registration(), "api_key": "should-not-be-in-file"}))
    with pytest.raises(ValueError, match="fields"):
        load_registration(path, manifest())


def test_registration_refuses_non_synthetic_manifest(tmp_path: Path) -> None:
    path = tmp_path / "registered.json"
    path.write_text(json.dumps(registration()))
    unsafe = {**manifest(), "synthetic_only": False}
    with pytest.raises(ValueError, match="synthetic Cartwheel"):
        load_registration(path, unsafe)


def test_registration_rejects_a_ready_path_outside_checkout(tmp_path: Path) -> None:
    path = tmp_path / "registered.json"
    path.write_text(json.dumps({**registration(), "ready_path": "/health"}))
    with pytest.raises(ValueError, match="checkout path"):
        load_registration(path, manifest())
