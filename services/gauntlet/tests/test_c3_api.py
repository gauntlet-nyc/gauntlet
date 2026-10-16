"""Session 3 API: Gate runs, Recall views, hash-bound approvals, sponsor status, settings."""

import json
import shutil
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from gauntlet.api.container import get_container
from gauntlet.api.main import app
from gauntlet.api.settings import REPO_ROOT, SettingsError, get_settings, load_settings
from gauntlet.integrations.history_files import HistoryArchive, HistoryIntegrityError

TOKEN = "dev-reviewer-token-0123456789"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    for name in ("DAYTONA_API_KEY", "ANCHOR_API_KEY", "RUN_LIVE_INTEGRATIONS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GAUNTLET_REVIEWER_TOKENS", f"reviewer-dev:{TOKEN}")
    get_settings.cache_clear()
    get_container.cache_clear()
    yield TestClient(app)
    get_settings.cache_clear()
    get_container.cache_clear()


def _start(client: TestClient, change_id: str = "help-button") -> dict:  # type: ignore[type-arg]
    response = client.post("/gate/runs", json={"change_id": change_id})
    assert response.status_code == 201
    return response.json()  # type: ignore[no-any-return]


def test_help_button_run_uses_real_pipeline_with_offline_labels(client: TestClient) -> None:
    run = _start(client)
    assert run["status"] == "confirmed_regression"
    assert run["attribution"] == "introduced"
    sides = [(a["revision"], a["outcome"]) for a in run["attempts"]]
    assert sides == [("head", "fail"), ("head", "fail"), ("base", "pass"), ("base", "pass")]
    labels = {p["provider"] for p in run["provenance"]}
    assert {"model:offline_scripted", "sandbox:offline_fake"} <= labels
    assert not any(p["live"] for p in run["provenance"])
    assert run["events"][1]["event_type"] == "plan_frozen"
    assert run["events"][1]["payload"]["plan_hash"] == run["plan_sha256"]
    assert "src/components/FloatingHelp.module.css" in {d["path"] for d in run["diff"]}
    assert run["attacks"] and run["attacks"][0]["worker_kind"] == "ui"
    shot = run["attempts"][0]["screenshot_artifact_ids"][0]
    image = client.get(f"/gate/runs/{run['run_id']}/artifacts/{shot}")
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"
    assert client.get(f"/gate/runs/{run['run_id']}/artifacts/nope").status_code == 404
    assert client.get(f"/gate/runs/{run['run_id']}").json() == run
    assert client.get("/gate/runs").json()[0]["offline"] is True
    assert client.get("/gate/runs/nope").status_code == 404


def test_clean_change_passes_on_both_revisions(client: TestClient) -> None:
    run = _start(client, "clean")
    assert run["status"] == "passed"
    assert run["fix_plan"] is None
    assert all(a["outcome"] == "pass" for a in run["attempts"])


def test_refund_tool_runs_ai_agent_route_against_real_tool_code(client: TestClient) -> None:
    run = _start(client, "refund-tool")
    assert run["status"] == "confirmed_regression"
    assert run["attribution"] == "introduced"
    sides = [(a["revision"], a["outcome"]) for a in run["attempts"]]
    assert sides == [("head", "fail"), ("head", "fail"), ("base", "pass"), ("base", "pass")]
    assert "Forbidden refund recorded" in run["attempts"][0]["observed"]
    assert "sandbox:local_tool_world" in {p["provider"] for p in run["provenance"]}
    assert run["diff"][0]["path"] == "api/src/tools/request_refund.ts"
    assert run["fix_plan"]["allowed_paths"] == ["api/src/tools/request_refund.ts"]


def test_briefing_is_templated_from_findings(client: TestClient) -> None:
    run = _start(client, "clean")
    body = client.get(f"/gate/runs/{run['run_id']}/briefing").json()
    assert body["briefing"]["confirmed"] == 0
    assert "Run run-clean-" in body["briefing"]["spoken_summary"]
    assert body["provenance"]["live"] is False


def _fix_approval(run: dict, **overrides: str) -> dict:  # type: ignore[type-arg]
    body = {
        "run_id": run["run_id"],
        "subject": "fix_plan",
        "subject_id": run["fix_plan"]["plan"]["fix_plan_id"],
        "plan_sha256": run["fix_plan"]["plan_sha256"],
        "decision": "approved",
    }
    return {**body, **overrides}


def test_fix_plan_approval_needs_token_and_exact_hash(client: TestClient) -> None:
    run = _start(client)
    assert client.post("/approvals", json=_fix_approval(run)).status_code == 401
    bad = {"Authorization": "Bearer wrong-token-0123456789"}
    assert client.post("/approvals", json=_fix_approval(run), headers=bad).status_code == 401
    stale = _fix_approval(run, plan_sha256="0" * 64)
    assert client.post("/approvals", json=stale, headers=AUTH).status_code == 409
    no_reason = _fix_approval(run, decision="rejected")
    assert client.post("/approvals", json=no_reason, headers=AUTH).status_code == 422
    ok = client.post("/approvals", json=_fix_approval(run), headers=AUTH)
    assert ok.status_code == 201
    record = ok.json()["record"]
    assert record["reviewer_id"] == "reviewer-dev"
    assert record["allowed_paths"] == ["src/components/FloatingHelp.module.css"]
    events = client.get(f"/gate/runs/{run['run_id']}").json()["events"]
    assert events[-1]["event_type"] == "approval_recorded"
    assert client.get("/approvals").json()[0]["approval_id"] == record["approval_id"]


def test_reviewer_identity_cannot_come_from_body(client: TestClient) -> None:
    run = _start(client)
    body = {**_fix_approval(run), "reviewer_id": "mallory"}
    response = client.post("/approvals", json=body, headers=AUTH)
    assert response.status_code == 201
    assert response.json()["record"]["reviewer_id"] == "reviewer-dev"


def test_recall_audit_uses_ledger_not_caller_mismatch(client: TestClient) -> None:
    audit = client.get("/recall/audit").json()
    summary = audit["summary"]
    assert (summary["violations"], summary["inconclusive"]) == (3, 1)
    assert summary["audited"] == summary["violations"] + summary["clear"] + summary["inconclusive"]
    violations = {
        v["tool_event_id"] for v in audit["verdicts"] if v["classification"] == "audit_violation"
    }
    assert violations == {"tool-event-001", "tool-event-009", "tool-event-015"}
    assert all(not p["live"] for p in audit["provenance"])
    assert {p["action"] for p in audit["proposals"]} == {
        "reverse_transaction_review",
        "collect_missing_evidence",
    }


def test_recall_counterfactual_classes_and_lineage(client: TestClient) -> None:
    view = client.get("/recall/counterfactual").json()
    by_decision = {c["decision_id"]: c["verdict"]["classification"] for c in view["cases"]}
    assert by_decision == {
        "decision-001": "tainted",
        "decision-004": "cleared",
        "decision-015": "tainted",
        "decision-007": "not_replayable",
        "decision-009": "tainted",
        "decision-012": "cleared",
    }
    second_order = {c["decision_id"] for c in view["cases"] if not c["exposure"]["direct"]}
    assert second_order == {"decision-007", "decision-009", "decision-012"}
    assert any("OFFLINE" in p["label"] for p in view["provenance"])
    edges = client.get("/recall/lineage/decision-009").json()["edges"]
    assert [e["relation"] for e in edges][0] == "derived_into"
    assert client.get("/recall/lineage/decision-002").status_code == 404
    assert len(client.get("/recall/timeline").json()) == 42


def test_review_queue_approval_is_review_only(client: TestClient) -> None:
    queue = client.get("/recall/review-queue").json()
    item = next(i for i in queue if i["kind"] == "remediation_proposal")
    assert item["status"] == "pending"
    body = {
        "run_id": item["recall_id"],
        "subject": "remediation",
        "subject_id": item["item_id"],
        "plan_sha256": item["plan_sha256"],
        "decision": "approved",
    }
    response = client.post("/approvals", json=body, headers=AUTH)
    assert response.status_code == 201
    assert "Nothing was reversed" in response.json()["note"]
    after = {i["item_id"]: i for i in client.get("/recall/review-queue").json()}
    assert after[item["item_id"]]["status"] == "approved_for_review"


def test_sponsors_never_claim_live_and_never_echo_values(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANCHOR_API_KEY", "sk-should-never-appear")
    get_settings.cache_clear()
    get_container.cache_clear()
    response = client.get("/sponsors")
    assert "sk-should-never-appear" not in response.text
    rows = {r["sponsor"]: r for r in response.json()}
    assert rows["Anchor"]["configured"] is True
    assert rows["Daytona"]["missing_env"][0] == "DAYTONA_API_KEY"
    assert {r["status"] for r in rows.values()} == {"offline-tested, live NOT RUN"}


def test_settings_validate_and_hide_tokens() -> None:
    with pytest.raises(SettingsError, match="RUN_LIVE_INTEGRATIONS"):
        load_settings({"RUN_LIVE_INTEGRATIONS": "yes"})
    assert (
        load_settings({"GAUNTLET_REVIEWER_TOKENS": "REPLACE_WITH_name:token"}).reviewer_for(
            "REPLACE_WITH_name"
        )
        is None
    )
    with pytest.raises(SettingsError, match="GAUNTLET_MODEL_PROVIDER"):
        load_settings({"GAUNTLET_MODEL_PROVIDER": "openai"})
    with pytest.raises(SettingsError, match="16"):
        load_settings({"GAUNTLET_REVIEWER_TOKENS": "r:short"})
    settings = load_settings({"GAUNTLET_REVIEWER_TOKENS": f"r:{TOKEN}"})
    assert TOKEN not in repr(settings)
    assert settings.anchor_require_proxy is True
    assert load_settings({"GAUNTLET_ANCHOR_REQUIRE_PROXY": "0"}).anchor_require_proxy is False
    assert settings.reviewer_for(TOKEN) is not None and settings.reviewer_for("x" * 20) is None


def test_tampered_history_is_refused(tmp_path: Path) -> None:
    copy = tmp_path / "history"
    shutil.copytree(REPO_ROOT / "apps/cartwheel/history", copy)
    ledger = copy / "ledger.json"
    ledger.write_text(
        ledger.read_text().replace("synthetic-customer-02", "synthetic-customer-03", 1)
    )
    with pytest.raises(HistoryIntegrityError):
        HistoryArchive.load(copy)


def test_adapter_selection_never_goes_live_without_opt_in() -> None:
    from gauntlet.api.services.gate import GateService
    from gauntlet.settings import Settings

    keys = {
        "DAYTONA_API_KEY": "k" * 20,
        "DAYTONA_TARGET": "eu",
        "GAUNTLET_DAYTONA_REGISTRATION": "/tmp/r.json",
        "ANCHOR_API_KEY": "k" * 20,
        "GAUNTLET_ANCHOR_REQUIRE_PROXY": "0",
        "GAUNTLET_MODEL_PROVIDER": "azure",
        "AZURE_OPENAI_ENDPOINT": "https://x.openai.azure.com",
        "AZURE_OPENAI_DEPLOYMENT": "d",
        "AZURE_OPENAI_API_KEY": "k" * 20,
    }
    assert GateService.adapters(Settings.from_env(keys)) == ("scripted", "fake", "fake")
    live = Settings.from_env({**keys, "RUN_LIVE_INTEGRATIONS": "1"})
    assert GateService.adapters(live) == ("azure", "daytona", "anchor")
    local = {
        "CARTWHEEL_BASE_ORIGIN": "http://127.0.0.1:3101",
        "CARTWHEEL_HEAD_ORIGIN": "http://127.0.0.1:3102",
    }
    assert GateService.adapters(Settings.from_env(local)) == ("scripted", "local", "local")
    assert GateService.adapters(Settings.from_env(local), "clean") == ("scripted", "fake", "fake")
    assert GateService.adapters(live, "refund-tool") == ("azure", "fake", "fake")


def test_check_run_preview_is_never_published(client: TestClient) -> None:
    run = _start(client)
    preview = client.get(f"/gate/runs/{run['run_id']}/check-run").json()
    assert preview["conclusion"] == "failure"
    assert preview["published"] is False
    assert "Not tested does not mean safe" in preview["summary"]
    clean = _start(client, "clean")
    passed = client.get(f"/gate/runs/{clean['run_id']}/check-run").json()
    assert passed["conclusion"] == "success"


def test_onboarding_lists_synthetic_targets_and_open_steps(client: TestClient) -> None:
    view = client.get("/onboarding").json()
    assert {t["fixture_id"] for t in view["targets"]} == {"baseline-v1", "refund-v1"}
    assert all(t["synthetic_only"] for t in view["targets"])
    steps = {s["step"]: s for s in view["steps"]}
    assert steps["Configure reviewer tokens"]["done"] is True
    github = steps["Install the GitHub App and bind the repository"]
    assert github["done"] is False and "GITHUB_APP_ID" in github["detail"]


def test_refund_repair_needs_hash_approval_and_spends_it_once(client: TestClient) -> None:
    run = _start(client, "refund-tool")
    fix = run["fix_plan"]
    assert fix["repairable"] is True
    assert fix["provenance"]["provider"] == "proposer:offline_scripted_fix"
    url = f"/gate/runs/{run['run_id']}/repair"
    assert client.post(url).status_code == 401
    assert client.post(url, headers=AUTH).status_code == 409
    approved = client.post("/approvals", json=_fix_approval(run), headers=AUTH)
    assert approved.status_code == 201
    repaired = client.post(url, headers=AUTH)
    assert repaired.status_code == 200
    repair = repaired.json()["repair"]
    assert repair["verdict"] == "fix_verified_review_required"
    assert {c["name"]: c["passed"] for c in repair["checks"]} == {
        "original_attack": True,
        "variant_0": True,
        "legitimate_workflow": True,
    }
    assert repair["touched_paths"] == ["api/src/tools/request_refund.ts"]
    assert "never merges" in repair["note"]
    assert client.post(url, headers=AUTH).status_code == 409  # approval already spent
    events = [e["event_type"] for e in repaired.json()["events"]]
    assert events[-2:] == ["repair_requested", "repair_verified"]


def test_ui_sample_fix_is_not_repairable(client: TestClient) -> None:
    run = _start(client)
    assert run["fix_plan"]["repairable"] is False
    response = client.post(f"/gate/runs/{run['run_id']}/repair", headers=AUTH)
    assert response.status_code == 422


def _webhook_client(monkeypatch: pytest.MonkeyPatch, **env: str) -> TestClient:
    from gauntlet.api.routes import webhooks

    for name, value in env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(webhooks, "_STATE", webhooks._WebhookState())
    get_settings.cache_clear()
    get_container.cache_clear()
    return TestClient(app)


GH_SECRET = "github-webhook-secret-0123456789"


def _github_post(
    client: TestClient,
    payload: dict,
    delivery: str,
    event: str = "pull_request",  # type: ignore[type-arg]
) -> httpx.Response:
    import hashlib
    import hmac

    body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(GH_SECRET.encode(), body, hashlib.sha256).hexdigest()
    headers = {
        "X-Hub-Signature-256": signature,
        "X-GitHub-Delivery": delivery,
        "X-GitHub-Event": event,
        "content-type": "application/json",
    }
    return client.post("/webhooks/github", content=body, headers=headers)


def _pr(repo: str, base: str, head: str) -> dict:  # type: ignore[type-arg]
    return {
        "action": "opened",
        "pull_request": {
            "number": 7,
            "title": "Add a floating Help button",
            "draft": False,
            "base": {"sha": base},
            "head": {"sha": head},
        },
        "repository": {"full_name": repo},
    }


def test_github_webhook_verifies_and_starts_only_registered_revisions(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert client.post("/webhooks/github", content=b"{}").status_code == 503
    hook = _webhook_client(
        monkeypatch,
        GITHUB_WEBHOOK_SECRET=GH_SECRET,
        GAUNTLET_GITHUB_REPOSITORIES="demo/cartwheel",
    )
    manifest = json.loads((REPO_ROOT / "apps/cartwheel/fixture-manifest.v1.json").read_text())
    base, head = manifest["git_refs"]["base_sha"], manifest["git_refs"]["head_sha"]
    bad = hook.post(
        "/webhooks/github",
        content=b"{}",
        headers={"X-Hub-Signature-256": "sha256=00", "X-GitHub-Delivery": "deliv-0001"},
    )
    assert bad.status_code == 401
    assert _github_post(hook, {}, "deliv-ping-01", "ping").json()["status"] == "ignored"
    unbound = _github_post(hook, _pr("evil/repo", base, head), "deliv-0002")
    assert unbound.json()["status"] == "ignored"
    accepted = _github_post(hook, _pr("demo/cartwheel", base, head), "deliv-0003")
    assert accepted.status_code == 202 and accepted.json()["status"] == "accepted"
    assert _github_post(hook, _pr("demo/cartwheel", base, head), "deliv-0003").status_code == 401
    runs = hook.get("/gate/runs").json()
    assert runs and runs[0]["change_id"] == "help-button"
    unknown = _github_post(hook, _pr("demo/cartwheel", "a" * 40, "b" * 40), "deliv-0004")
    assert unknown.json()["status"] == "ignored"


def test_elevenlabs_webhook_reads_findings_and_never_approves(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import time

    from gauntlet.security.webhooks import elevenlabs_signature

    secret = "voice-webhook-secret-0123456789"
    hook = _webhook_client(
        monkeypatch, VOICE_WEBHOOK_SECRET=secret, ELEVENLABS_AGENT_ID="agent_demo"
    )
    run = hook.post("/gate/runs", json={"change_id": "help-button"}).json()

    def call(payload: dict) -> object:  # type: ignore[type-arg]
        body = json.dumps(payload).encode()
        signature = elevenlabs_signature(secret.encode(), int(time.time()), body)
        return hook.post(
            "/webhooks/elevenlabs", content=body, headers={"ElevenLabs-Signature": signature}
        )

    summary = call({"call_id": "c1", "intent": "run_summary", "run_id": run["run_id"]})
    assert "1 confirmed" in summary.json()["spoken_text"]  # type: ignore[attr-defined]
    approve = call({"call_id": "c2", "intent": "approve", "run_id": run["run_id"]})
    assert approve.status_code == 401  # type: ignore[attr-defined]
    replay = call(
        {
            "call_id": "c3",
            "intent": "replay_request",
            "run_id": run["run_id"],
            "attack_id": run["attacks"][0]["attack_id"],
        }
    ).json()  # type: ignore[attr-defined]
    assert replay["replay_request"]["status"] == "pending_operator_confirmation"
    unsigned = hook.post("/webhooks/elevenlabs", content=b"{}")
    assert unsigned.status_code == 401
