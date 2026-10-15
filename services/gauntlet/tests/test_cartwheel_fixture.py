import importlib.util
import json
import shutil
from importlib import resources
from pathlib import Path
from types import ModuleType

import pytest
from fastapi.testclient import TestClient

from gauntlet.api.main import app

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "apps/cartwheel/fixture-manifest.v1.json"


def test_packaged_manifest_matches_registered_fixture() -> None:
    packaged = resources.files("gauntlet.api").joinpath(
        "fixtures", "cartwheel-fixture-manifest.v1.json"
    )
    assert packaged.read_bytes() == MANIFEST.read_bytes()


def _builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "build_cartwheel_fixture", ROOT / "scripts/build_cartwheel_fixture.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.skipif(shutil.which("git") is None, reason="git required")
def test_manifest_matches_rebuilt_fixture(tmp_path: Path) -> None:
    built = _builder().build(tmp_path / "cw")
    refs = json.loads(MANIFEST.read_text())
    assert refs["git_refs"]["base_sha"] == built["base_sha"]
    assert refs["git_refs"]["head_sha"] == built["head_sha"]
    assert refs["fixture_checksum_sha256"] == built["fixture_checksum_sha256"]


def test_fixture_templates_leak_no_answer_key() -> None:
    text = "\n".join(
        p.read_text().lower() for p in (ROOT / "apps/cartwheel/fixture").rglob("*") if p.is_file()
    )
    for banned in ("overlap", "obstruct", "occlu", "hidden truth", "answer key"):
        assert banned not in text


def test_change_request_route_uses_real_shas() -> None:
    body = TestClient(app).get("/targets/cartwheel/change-request").json()
    manifest = json.loads(MANIFEST.read_text())
    assert body["base_sha"] == manifest["git_refs"]["base_sha"]
    assert body["head_sha"] == manifest["git_refs"]["head_sha"]
    assert body["base_sha"] != body["head_sha"]
