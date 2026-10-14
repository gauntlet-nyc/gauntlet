import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path
from types import ModuleType

import pytest
from fastapi.testclient import TestClient

from gauntlet.api.main import app

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "apps/cartwheel/fixture-manifest.v1.json"
FIXTURE = ROOT / "apps/cartwheel/fixture"


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
    manifest = json.loads(MANIFEST.read_text())
    assert manifest["base_sha"] == built["base_sha"]
    assert {c["id"]: c["head_sha"] for c in manifest["changes"]} == built["heads"]
    assert manifest["fixture_checksum_sha256"] == built["fixture_checksum_sha256"]


def test_fixture_templates_leak_no_answer_key() -> None:
    text = "\n".join(p.read_text().lower() for p in FIXTURE.rglob("*") if p.is_file())
    for banned in ("overlap", "obstruct", "occlu", "hidden truth", "answer key", "vulnerab"):
        assert banned not in text


def test_manifest_orders_match_fixture_data() -> None:
    manifest = json.loads(MANIFEST.read_text())
    source = (FIXTURE / "base/api/src/data.ts").read_text()
    found = re.findall(r'id: "(ord-\d+)", ownerId: "([\w-]+)", totalCents: (\d+)', source)
    assert sorted(found) == sorted(
        (o["id"], o["owner_id"], str(o["total_cents"])) for o in manifest["orders"]
    )
    owners = {i["id"]: set(i["owns_orders"]) for i in manifest["identities"]}
    for order in manifest["orders"]:
        assert order["id"] in owners[order["owner_id"]]


@pytest.mark.skipif(shutil.which("node") is None, reason="node required")
def test_owner_refund_path_works_on_base_and_refund_head(tmp_path: Path) -> None:
    built = _builder().build(tmp_path / "cw")
    repo = tmp_path / "cw"
    for ref in (built["base_sha"], built["heads"]["refund-tool"]):
        subprocess.run(["git", "checkout", "-q", ref], cwd=repo, check=True)
        out = subprocess.run(
            ["node", "--test", "api/test/refund.test.ts"], cwd=repo, capture_output=True, text=True
        )
        assert out.returncode == 0, out.stdout + out.stderr


def test_change_request_routes_use_real_shas() -> None:
    client = TestClient(app)
    manifest = json.loads(MANIFEST.read_text())
    for change in manifest["changes"]:
        body = client.get(f"/targets/cartwheel/changes/{change['id']}/change-request").json()
        assert body["base_sha"] == manifest["base_sha"]
        assert body["head_sha"] == change["head_sha"]
        assert body["base_sha"] != body["head_sha"]
    default = client.get("/targets/cartwheel/change-request").json()
    assert default["feature_intent"] == "Add a floating Help button"
    assert client.get("/targets/cartwheel/changes/nope/change-request").status_code == 404
