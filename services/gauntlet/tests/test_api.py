from fastapi.testclient import TestClient

from gauntlet.api.main import app


def test_health_is_explicit_about_scaffold_state() -> None:
    resp = TestClient(app).get("/health")
    assert resp.status_code == 200
    assert resp.json()["provider_integrations"] == "not-implemented"
