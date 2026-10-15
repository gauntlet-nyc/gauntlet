from fastapi.testclient import TestClient

from gauntlet.api.main import app

client = TestClient(app)


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
