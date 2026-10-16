"""GitHub App publisher, webhook verification and ElevenLabs adapter (offline)."""

import asyncio
import base64
import hashlib
import hmac
import json
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest

from gauntlet.contracts import VoiceBriefing
from gauntlet.intake.github import EventIgnored, RepositoryBinding, RunRequested
from gauntlet.integrations.elevenlabs import ElevenLabsVoice
from gauntlet.integrations.github_app import (
    GitHubAppCheckRunPublisher,
    app_jwt,
    parse_rsa_private_key,
)
from gauntlet.ports.code_host import CheckRunReport
from gauntlet.ports.errors import EnvironmentUnavailableError
from gauntlet.security.webhooks import (
    ElevenLabsWebhookVerifier,
    GitHubWebhookVerifier,
    ReplayGuard,
    WebhookRejectedError,
    elevenlabs_signature,
)
from gauntlet.settings import MissingSettingError, load_settings

OPENSSL = shutil.which("openssl")
needs_openssl = pytest.mark.skipif(OPENSSL is None, reason="openssl not installed")
SECRET = b"synthetic-webhook-secret-0123456789"
SHA = "a" * 40
REPORT = CheckRunReport("Gauntlet", "failure", "1 confirmed issue", "summary", None)


@pytest.fixture(scope="module")
def key_pem(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if OPENSSL is None:
        pytest.skip("openssl not installed")
    path = tmp_path_factory.mktemp("ghkey") / "app.pem"
    subprocess.run(
        [OPENSSL, "genrsa", "-traditional", "-out", str(path), "2048"],
        check=True,
        capture_output=True,
    )
    return path


@needs_openssl
def test_jwt_signature_verifies_with_openssl(key_pem: Path, tmp_path: Path) -> None:
    key = parse_rsa_private_key(key_pem.read_text())
    token = app_jwt("12345", key, now=1_700_000_000)
    header, payload, signature = token.split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
    assert claims == {"iat": 1_699_999_940, "exp": 1_700_000_480, "iss": "12345"}
    assert json.loads(base64.urlsafe_b64decode(header + "=="))["alg"] == "RS256"
    assert OPENSSL is not None
    public = tmp_path / "pub.pem"
    subprocess.run(
        [OPENSSL, "rsa", "-in", str(key_pem), "-pubout", "-out", str(public)],
        check=True,
        capture_output=True,
    )
    (tmp_path / "msg").write_bytes(f"{header}.{payload}".encode())
    (tmp_path / "sig").write_bytes(base64.urlsafe_b64decode(signature + "=="))
    result = subprocess.run(
        [
            OPENSSL,
            "dgst",
            "-sha256",
            "-verify",
            str(public),
            "-signature",
            str(tmp_path / "sig"),
            str(tmp_path / "msg"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert repr(key) == "RsaPrivateKey(bits=2048)"


@needs_openssl
def test_pkcs8_key_also_parses(key_pem: Path, tmp_path: Path) -> None:
    assert OPENSSL is not None
    pkcs8 = tmp_path / "k8.pem"
    subprocess.run(
        [OPENSSL, "pkcs8", "-topk8", "-nocrypt", "-in", str(key_pem), "-out", str(pkcs8)],
        check=True,
        capture_output=True,
    )
    assert parse_rsa_private_key(pkcs8.read_text()) == parse_rsa_private_key(key_pem.read_text())


def test_rejects_non_rsa_material() -> None:
    with pytest.raises(ValueError):
        parse_rsa_private_key("not a key")


@needs_openssl
def test_publisher_token_then_create_then_update(key_pem: Path) -> None:
    calls: list[tuple[str, str, dict[str, object] | None]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, request.url.path, body))
        if request.url.path.endswith("/access_tokens"):
            assert request.headers["authorization"].startswith("Bearer ")
            assert body == {"permissions": {"checks": "write"}}
            return httpx.Response(201, json={"token": "ghs_synthetic"})
        assert request.headers["authorization"] == "token ghs_synthetic"
        if request.method == "GET":
            return httpx.Response(200, json={"check_runs": [{"id": 5, "external_id": "other-run"}]})
        if request.method == "POST":
            return httpx.Response(201, json={"id": 77})
        return httpx.Response(200, json={"id": 77})

    publisher = GitHubAppCheckRunPublisher(
        app_id="1",
        installation_id="2",
        private_key=parse_rsa_private_key(key_pem.read_text()),
        transport=httpx.MockTransport(handle),
    )

    async def scenario() -> None:
        assert await publisher.publish("acme/shop", SHA, "gh-run-1", REPORT) == "77"
        assert await publisher.publish("acme/shop", SHA, "gh-run-1", REPORT) == "77"
        with pytest.raises(ValueError):
            await publisher.publish("acme/shop", "abc", "gh-run-1", REPORT)

    asyncio.run(scenario())
    methods = [(m, p) for m, p, _ in calls]
    assert methods == [
        ("POST", "/app/installations/2/access_tokens"),
        ("GET", f"/repos/acme/shop/commits/{SHA}/check-runs"),
        ("POST", "/repos/acme/shop/check-runs"),
        ("PATCH", "/repos/acme/shop/check-runs/77"),
    ]
    created = calls[2][2]
    assert created is not None and created["external_id"] == "gh-run-1"
    assert created["conclusion"] == "failure" and created["status"] == "completed"
    assert not any("merge" in p or "comments" in p or "reviews" in p for _, p in methods)


def test_publisher_from_settings_needs_keys() -> None:
    with pytest.raises(MissingSettingError, match="GITHUB_APP_ID"):
        GitHubAppCheckRunPublisher.from_settings(load_settings({}))


def _gh_headers(
    body: bytes, delivery: str = "11111111-2222", event: str = "pull_request"
) -> dict[str, str]:
    digest = hmac.new(SECRET, body, hashlib.sha256).hexdigest()
    return {
        "X-Hub-Signature-256": f"sha256={digest}",
        "X-GitHub-Delivery": delivery,
        "X-GitHub-Event": event,
    }


def test_github_webhook_signature_replay_and_mapping() -> None:
    bindings = {"acme/shop": RepositoryBinding("cartwheel", "cartwheel-fixture", "fixture-1", 500)}
    verifier = GitHubWebhookVerifier(SECRET, bindings)
    body = json.dumps(
        {
            "action": "opened",
            "number": 7,
            "pull_request": {
                "number": 7,
                "title": "Add help button",
                "draft": False,
                "head": {"sha": SHA},
                "base": {"sha": "b" * 40},
            },
            "repository": {"full_name": "acme/shop"},
            "installation": {"id": 2},
        }
    ).encode()
    result = verifier.handle(_gh_headers(body), body)
    assert isinstance(result, RunRequested), result
    assert result.head_sha == SHA and result.change.target_id == "cartwheel-fixture"
    with pytest.raises(WebhookRejectedError, match="duplicate"):
        verifier.handle(_gh_headers(body), body)
    with pytest.raises(WebhookRejectedError, match="invalid signature"):
        verifier.handle(
            {**_gh_headers(body, "33333333-4444"), "X-Hub-Signature-256": "sha256=" + "0" * 64},
            body,
        )
    ping = b"{}"
    assert isinstance(
        verifier.handle(_gh_headers(ping, "55555555-6666", "ping"), ping), EventIgnored
    )


def test_replay_guard_expires() -> None:
    now = [0.0]
    guard = ReplayGuard(ttl_seconds=10, clock=lambda: now[0])
    guard.accept_once("a")
    with pytest.raises(WebhookRejectedError):
        guard.accept_once("a")
    now[0] = 11
    guard.accept_once("a")


def _voice(clock: float = 1_700_000_000) -> ElevenLabsWebhookVerifier:
    return ElevenLabsWebhookVerifier(SECRET, agent_id="agent_1", clock=lambda: clock)


def test_voice_webhook_read_intent_and_caller_from_signature() -> None:
    body = json.dumps({"call_id": "c1", "intent": "run_summary", "run_id": "run-1"}).encode()
    headers = {"ElevenLabs-Signature": elevenlabs_signature(SECRET, 1_700_000_000, body)}
    call = _voice().parse_tool_call(headers, body)
    assert call.caller_ref == "elevenlabs-agent-agent_1" and call.intent == "run_summary"


@pytest.mark.parametrize(
    "payload",
    [
        {"call_id": "c1", "intent": "approve_fix", "run_id": "run-1"},
        {"call_id": "c1", "intent": "run_summary", "run_id": "run-1", "caller_ref": "admin"},
        {"call_id": "c1", "intent": "replay_request", "run_id": "run-1"},
    ],
)
def test_voice_webhook_rejects_unsafe_requests(payload: dict[str, str]) -> None:
    body = json.dumps(payload).encode()
    headers = {"ElevenLabs-Signature": elevenlabs_signature(SECRET, 1_700_000_000, body)}
    with pytest.raises(WebhookRejectedError):
        _voice().parse_tool_call(headers, body)


def test_voice_webhook_rejects_bad_or_stale_signature() -> None:
    body = b'{"call_id":"c1","intent":"run_summary","run_id":"r"}'
    stale = {"ElevenLabs-Signature": elevenlabs_signature(SECRET, 1_600_000_000, body)}
    with pytest.raises(WebhookRejectedError, match="stale"):
        _voice().parse_tool_call(stale, body)
    forged = {"ElevenLabs-Signature": elevenlabs_signature(b"x" * 32, 1_700_000_000, body)}
    with pytest.raises(WebhookRejectedError, match="invalid signature"):
        _voice().parse_tool_call(forged, body)
    with pytest.raises(WebhookRejectedError, match="missing"):
        _voice().parse_tool_call({}, body)


def test_elevenlabs_client_signed_url_and_tts() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.headers["xi-api-key"] == "synthetic-key"
        if request.url.path == "/v1/convai/conversation/get-signed-url":
            assert request.url.params["agent_id"] == "agent_1"
            return httpx.Response(200, json={"signed_url": "wss://api.elevenlabs.io/x?token=t"})
        assert request.url.path == "/v1/text-to-speech/voice_1"
        assert json.loads(request.content)["text"].startswith("Run run-1")
        return httpx.Response(200, content=b"ID3audio")

    voice = ElevenLabsVoice(
        api_key="synthetic-key",
        agent_id="agent_1",
        voice_id="voice_1",
        transport=httpx.MockTransport(handle),
    )
    briefing = VoiceBriefing(
        run_id="run-1",
        source_event_sequence=3,
        findings=(),
        confirmed=0,
        suspected=0,
        not_tested=0,
        coverage_gaps=0,
        spoken_summary="Run run-1: 0 confirmed.",
    )

    async def scenario() -> None:
        assert (await voice.signed_conversation_url()).startswith("wss://")
        assert await voice.speak_briefing(briefing) == b"ID3audio"

    asyncio.run(scenario())


def test_elevenlabs_needs_live_flag_and_keys() -> None:
    with pytest.raises(EnvironmentUnavailableError, match="RUN_LIVE_INTEGRATIONS"):
        ElevenLabsVoice.from_settings(load_settings({}))
    with pytest.raises(MissingSettingError, match="ELEVENLABS_API_KEY"):
        ElevenLabsVoice.from_settings(load_settings({"RUN_LIVE_INTEGRATIONS": "1"}))
