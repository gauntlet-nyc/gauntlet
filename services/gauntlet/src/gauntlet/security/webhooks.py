"""Verified inbound webhooks (GitHub App, ElevenLabs). Framework-agnostic: an API route
passes raw headers + body and gets back a verified, typed result or an exception.

Nothing in a body is trusted until its HMAC verifies. Deliveries are single-use (replay
cache), ElevenLabs timestamps must be fresh, and the voice `caller_ref` comes from the
verified signature context, never from what was said.
"""

import hashlib
import hmac
import json
import re
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Final

from pydantic import ValidationError

from gauntlet.contracts import VoiceToolCall
from gauntlet.intake.github import (
    EventIgnored,
    RepositoryBinding,
    RunRequested,
    handle_pull_request_event,
    verify_signature,
)

_MAX_BODY: Final = 1_000_000
_DELIVERY: Final = re.compile(r"^[A-Za-z0-9-]{8,128}$")
ELEVENLABS_TOLERANCE_SECONDS: Final = 30 * 60


class WebhookRejectedError(Exception):
    """The request is not authentic or not acceptable. `reason` is safe to log/return."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ReplayGuard:
    """Remembers delivery IDs for `ttl_seconds`; a repeat is rejected. Bounded memory."""

    def __init__(
        self,
        ttl_seconds: float = 24 * 3600,
        max_entries: int = 50_000,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._clock = clock
        self._seen: OrderedDict[str, float] = OrderedDict()

    def accept_once(self, key: str) -> None:
        now = self._clock()
        while self._seen and next(iter(self._seen.values())) < now - self._ttl:
            self._seen.popitem(last=False)
        if key in self._seen:
            raise WebhookRejectedError("duplicate delivery")
        if len(self._seen) >= self._max:
            self._seen.popitem(last=False)
        self._seen[key] = now


def _header(headers: Mapping[str, str], name: str) -> str | None:
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value
    return None


class GitHubWebhookVerifier:
    """Verify `X-Hub-Signature-256`, de-duplicate `X-GitHub-Delivery`, map PR events."""

    def __init__(
        self,
        secret: bytes,
        bindings: Mapping[str, RepositoryBinding],
        *,
        replay_guard: ReplayGuard | None = None,
    ) -> None:
        if len(secret) < 16:
            raise ValueError("GitHub webhook secret must be at least 16 bytes")
        self._secret = secret
        self._bindings = bindings
        self._guard = replay_guard or ReplayGuard()

    def handle(self, headers: Mapping[str, str], body: bytes) -> RunRequested | EventIgnored:
        if len(body) > _MAX_BODY:
            raise WebhookRejectedError("body too large")
        if not verify_signature(self._secret, body, _header(headers, "X-Hub-Signature-256")):
            raise WebhookRejectedError("invalid signature")
        delivery = _header(headers, "X-GitHub-Delivery")
        if delivery is None or not _DELIVERY.fullmatch(delivery):
            raise WebhookRejectedError("missing delivery ID")
        self._guard.accept_once(f"github:{delivery}")
        event = _header(headers, "X-GitHub-Event")
        if event == "ping":
            return EventIgnored("ping")
        if event != "pull_request":
            return EventIgnored(f"event {event!r} is not handled")
        try:
            payload = json.loads(body)
        except ValueError:
            raise WebhookRejectedError("body is not JSON") from None
        if not isinstance(payload, dict):
            raise WebhookRejectedError("body is not an object")
        return handle_pull_request_event(payload, self._bindings)


def elevenlabs_signature(secret: bytes, timestamp: int, body: bytes) -> str:
    """`ElevenLabs-Signature` value: `t=<unix>,v0=<hex HMAC-SHA256(secret, "t.body")>`."""
    digest = hmac.new(secret, f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v0={digest}"


class ElevenLabsWebhookVerifier:
    """Verify an ElevenLabs tool/webhook call and turn it into a `VoiceToolCall`.

    Expected JSON body (configured as the agent's server-tool payload):
    `{"call_id", "intent", "run_id"?, "finding_id"?, "attack_id"?}`. Unknown intents, extra
    fields and approve/merge/refund-style requests are rejected by the contract itself.
    """

    def __init__(
        self,
        secret: bytes,
        *,
        agent_id: str,
        replay_guard: ReplayGuard | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if len(secret) < 16:
            raise ValueError("voice webhook secret must be at least 16 bytes")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", agent_id):
            raise ValueError("ElevenLabs agent ID is invalid")
        self._secret = secret
        self._caller_ref = f"elevenlabs-agent-{agent_id}"
        self._guard = replay_guard or ReplayGuard()
        self._clock = clock

    def verify(self, headers: Mapping[str, str], body: bytes) -> None:
        if len(body) > _MAX_BODY:
            raise WebhookRejectedError("body too large")
        header = _header(headers, "ElevenLabs-Signature")
        if not header:
            raise WebhookRejectedError("missing signature")
        parts = dict(item.split("=", 1) for item in header.split(",") if "=" in item)
        timestamp, provided = parts.get("t", ""), parts.get("v0", "")
        if not timestamp.isdigit() or not provided:
            raise WebhookRejectedError("malformed signature")
        if abs(self._clock() - int(timestamp)) > ELEVENLABS_TOLERANCE_SECONDS:
            raise WebhookRejectedError("stale signature")
        expected = elevenlabs_signature(self._secret, int(timestamp), body).split("v0=", 1)[1]
        if not hmac.compare_digest(expected, provided):
            raise WebhookRejectedError("invalid signature")
        self._guard.accept_once(f"elevenlabs:{timestamp}:{provided}")

    def parse_tool_call(self, headers: Mapping[str, str], body: bytes) -> VoiceToolCall:
        self.verify(headers, body)
        try:
            raw = json.loads(body)
        except ValueError:
            raise WebhookRejectedError("body is not JSON") from None
        if not isinstance(raw, dict):
            raise WebhookRejectedError("body is not an object")
        allowed = {"call_id", "intent", "run_id", "finding_id", "attack_id"}
        if set(raw) - allowed:
            raise WebhookRejectedError("unexpected fields")
        try:
            return VoiceToolCall(
                **raw,
                caller_ref=self._caller_ref,
                received_at=datetime.fromtimestamp(self._clock(), UTC),
            )
        except (ValidationError, TypeError):
            raise WebhookRejectedError("not a permitted voice request") from None
