"""Snapshot registration binds the committed baseline bytes and deterministic revisions."""

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from gauntlet.execution.provider_smoke_config import load_registration

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "apps/cartwheel/fixture-manifest.v1.json"
STATE = ROOT / "apps/cartwheel/fixture/base/fixture-state.json"


def script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def options() -> dict[str, object]:
    return {
        "base_snapshot": "cartwheel-base-actual",
        "head_snapshot": "cartwheel-head-actual",
        "image_digest": "a" * 64,
        "repo_path": "/workspace/cartwheel",
        "preview_port": 3000,
        "preview_domain_suffix": ".proxy.daytona.work",
    }


def test_rebuilt_revisions_share_baseline_and_match_manifest(tmp_path: Path) -> None:
    builder = script("build_cartwheel_fixture")
    manifest = json.loads(MANIFEST.read_text())
    repo = tmp_path / "fixture"
    built = builder.build(repo)
    assert built["base_sha"] == manifest["git_refs"]["base_sha"]
    assert built["head_sha"] == manifest["git_refs"]["head_sha"]
    assert built["fixture_checksum_sha256"] == manifest["fixture_checksum_sha256"]
    for sha in (built["base_sha"], built["head_sha"]):
        builder.git(repo, "checkout", "--detach", sha)
        assert (repo / "fixture-state.json").read_bytes() == STATE.read_bytes()
    state = json.loads(STATE.read_text())
    assert state["synthetic_only"] is True
    assert state["fixture_id"] == manifest["fixture_id"]
    assert state["initial_orders"] == []


def test_registration_is_accepted_by_existing_loader(tmp_path: Path) -> None:
    module = script("prepare_cartwheel_registration")
    raw = module.prepare_registration(**options())
    destination = tmp_path / "registration.json"
    destination.write_text(json.dumps(raw))
    manifest = json.loads(MANIFEST.read_text())
    change, target = load_registration(destination, manifest)
    assert target.fixture_state_digest == hashlib.sha256(STATE.read_bytes()).hexdigest()
    assert target.fixture_state_path == "/workspace/cartwheel/fixture-state.json"
    assert change.base_sha == manifest["git_refs"]["base_sha"]
    assert change.head_sha == manifest["git_refs"]["head_sha"]
    assert {entry.image_digest for entry in target.snapshots} == {"a" * 64}
    assert len(raw) == 10
    assert all(
        set(entry) == {"source_sha", "snapshot", "image_digest"} for entry in raw["snapshots"]
    )


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("base_snapshot", "REPLACE_ME"),
        ("head_snapshot", "bad/name"),
        ("head_snapshot", "cartwheel-base-actual"),
        ("image_digest", "sha256:" + "a" * 64),
        ("repo_path", "relative/path"),
        ("repo_path", "/workspace/../cartwheel"),
        ("repo_path", "/workspace//cartwheel"),
        ("preview_port", 0),
        ("preview_domain_suffix", ".bad..example"),
        ("preview_domain_suffix", "https://example.com"),
    ],
)
def test_invalid_operator_inputs_rejected(key: str, value: object) -> None:
    module = script("prepare_cartwheel_registration")
    with pytest.raises(ValueError):
        module.prepare_registration(**{**options(), key: value})


def test_cli_writes_valid_registration_without_overwriting(tmp_path: Path) -> None:
    import subprocess
    import sys

    destination = tmp_path / "registration.json"
    arguments = [sys.executable, str(ROOT / "scripts/prepare_cartwheel_registration.py")]
    for key, value in options().items():
        arguments.extend(["--" + key.replace("_", "-"), str(value)])
    arguments.extend(["--output", str(destination)])
    result = subprocess.run(arguments, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "not_tested"
    assert report["snapshots_verified"] is False
    load_registration(destination, json.loads(MANIFEST.read_text()))
    original = destination.read_bytes()
    repeated = subprocess.run(arguments, capture_output=True, text=True, check=False)
    assert repeated.returncode == 1
    assert json.loads(repeated.stdout)["error_type"] == "FileExistsError"
    assert destination.read_bytes() == original
