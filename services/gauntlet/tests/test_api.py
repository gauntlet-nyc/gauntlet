from importlib import resources
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gauntlet.api.main import app

client = TestClient(app)
GOLDENS = Path(__file__).resolve().parents[3] / "docs/contracts/examples"


@pytest.mark.parametrize(
    "name", ("ui-plan.v1.json", "observation.v1.json", "run-event.v1.json")
)
def test_packaged_offline_fixtures_match_canonical_goldens(name: str) -> None:
    packaged = resources.files("gauntlet.api").joinpath("fixtures", name).read_bytes()
    assert packaged == (GOLDENS / name).read_bytes()


def test_health_is_explicit_about_scaffold_state() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["provider_integrations"] == "not-implemented"


def test_fake_run_serves_frozen_golden_plan() -> None:
    body = client.get("/runs/fake").json()
    assert body["label"].startswith("FAKE RUN")
    assert body["plan"]["attack_id"] == "attack-ui-001"
    assert body["events"][0]["event_type"] == "plan_frozen"
    assert body["run_id"] == body["events"][0]["run_id"]


def test_fake_run_page_is_labelled_fake() -> None:
    resp = client.get("/fake-run")
    assert resp.status_code == 200
    assert "FAKE RUN" in resp.text
    assert "attack-ui-001" in resp.text


def test_offline_gate_checkpoint_reports_regression_from_recordings() -> None:
    body = client.get("/runs/offline-gate").json()
    assert body["execution_mode"] == "offline_recording"
    assert body["oracle_outcomes"] == ["fail", "fail", "pass"]
    assert body["status"] == "confirmed_regression"
    assert body["attribution"] == "introduced"
    assert [e["sequence"] for e in body["events"]] == [1, 2]
