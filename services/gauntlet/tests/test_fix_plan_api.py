import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from gauntlet.api.auth import TOKENS_ENV
from gauntlet.api.main import create_app

TOKEN = "test-token-not-a-secret"
URL = "/v1/fix-plans/fix-001"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    table = {TOKEN: {"reviewer_id": "reviewer-1", "channel": "dashboard"}}
    monkeypatch.setenv(TOKENS_ENV, json.dumps(table))
    return TestClient(create_app())


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def _decision(plan_sha256: str, **extra: str) -> dict[str, Any]:
    return {
        "subject": "fix_plan",
        "subject_id": "fix-001",
        "plan_sha256": plan_sha256,
        "decision": "approved",
        **extra,
    }


def test_get_returns_plan_hash_and_no_approvals_yet(client: TestClient) -> None:
    body = client.get(URL).json()
    assert len(body["plan_sha256"]) == 64
    assert body["approvals"] == []
    assert body["label"].startswith("DEMO")


def test_approve_requires_authentication(client: TestClient) -> None:
    sha = client.get(URL).json()["plan_sha256"]
    assert client.post(f"{URL}/approve", json=_decision(sha)).status_code == 401
    bad = {"Authorization": "Bearer wrong"}
    assert client.post(f"{URL}/approve", json=_decision(sha), headers=bad).status_code == 401


def test_approve_refused_when_no_token_table_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(TOKENS_ENV)
    sha = client.get(URL).json()["plan_sha256"]
    resp = client.post(f"{URL}/approve", json=_decision(sha), headers=_auth())
    assert resp.status_code == 401


def test_approval_binds_to_hash_and_server_side_identity(client: TestClient) -> None:
    view = client.get(URL).json()
    resp = client.post(f"{URL}/approve", json=_decision(view["plan_sha256"]), headers=_auth())
    assert resp.status_code == 200
    record = resp.json()
    assert record["reviewer_id"] == "reviewer-1"
    assert record["channel"] == "dashboard"
    assert record["plan_sha256"] == view["plan_sha256"]
    assert record["allowed_paths"] == view["fix_plan"]["allowed_paths"]
    assert len(client.get(URL).json()["approvals"]) == 1


def test_reviewer_id_in_body_is_rejected(client: TestClient) -> None:
    sha = client.get(URL).json()["plan_sha256"]
    resp = client.post(
        f"{URL}/approve", json=_decision(sha, reviewer_id="someone-else"), headers=_auth()
    )
    assert resp.status_code == 422


def test_stale_hash_is_refused(client: TestClient) -> None:
    resp = client.post(f"{URL}/approve", json=_decision("0" * 64), headers=_auth())
    assert resp.status_code == 409
    assert client.get(URL).json()["approvals"] == []


def test_voice_channel_cannot_be_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    table = {TOKEN: {"reviewer_id": "reviewer-1", "channel": "voice"}}
    monkeypatch.setenv(TOKENS_ENV, json.dumps(table))
    client = TestClient(create_app())
    sha = client.get(URL).json()["plan_sha256"]
    assert client.post(f"{URL}/approve", json=_decision(sha), headers=_auth()).status_code == 401


def test_rejection_needs_reason_and_is_recorded(client: TestClient) -> None:
    sha = client.get(URL).json()["plan_sha256"]
    missing = client.post(
        f"{URL}/approve", json=_decision(sha, decision="rejected"), headers=_auth()
    )
    assert missing.status_code == 422
    ok = client.post(
        f"{URL}/approve",
        json=_decision(sha, decision="rejected", reason="hides the Help button"),
        headers=_auth(),
    )
    assert ok.status_code == 200 and ok.json()["decision"] == "rejected"
    assert ok.json()["allowed_paths"] == []


def test_wrong_subject_or_unknown_plan(client: TestClient) -> None:
    sha = client.get(URL).json()["plan_sha256"]
    other = _decision(sha, subject_id="fix-999")
    assert client.post(f"{URL}/approve", json=other, headers=_auth()).status_code == 422
    assert client.get("/v1/fix-plans/nope").status_code == 404
