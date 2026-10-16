"""Typed API settings, read once from environment variables.

Keys are never stored on this object: for provider credentials only *whether* a variable is set
is recorded, so nothing here can print, log or serialize a secret value.
"""

import hmac
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Literal

REPO_ROOT = Path(__file__).resolve().parents[5]

# Sponsor/provider -> env var names that must all be set before a live call is possible.
PROVIDER_ENV: Mapping[str, tuple[str, ...]] = {
    "daytona": ("DAYTONA_API_KEY", "DAYTONA_API_URL", "DAYTONA_TARGET"),
    "anchor": ("ANCHOR_API_KEY",),
    "arize": ("ARIZE_API_KEY", "ARIZE_SPACE_ID"),
    "surrealdb": ("SURREALDB_URL", "SURREALDB_USER", "SURREALDB_PASS"),
    "surrealdb_agent_memory": ("SURREAL_MEMORY_URL",),
    "elevenlabs": ("ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID"),
    "azure_openai": ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_DEPLOYMENT"),
    "bedrock": ("AWS_REGION", "BEDROCK_MODEL_ID"),
    "github_app": ("GITHUB_APP_ID", "GITHUB_APP_PRIVATE_KEY", "GITHUB_WEBHOOK_SECRET"),
}

ModelProvider = Literal["azure", "bedrock"]


class SettingsError(ValueError):
    """A setting is present but malformed. The message names the variable, never its value."""


@dataclass(frozen=True)
class ReviewerToken:
    reviewer_id: str
    channel: Literal["dashboard", "api"]


@dataclass(frozen=True)
class ApiSettings:
    run_live_integrations: bool
    model_provider: ModelProvider
    anchor_require_proxy: bool
    history_dir: Path
    refund_manifest: Path
    configured_env: frozenset[str]
    _reviewer_tokens: Mapping[str, ReviewerToken] = field(repr=False)

    def provider_configured(self, provider: str) -> bool:
        return all(name in self.configured_env for name in PROVIDER_ENV[provider])

    def missing_env(self, provider: str) -> tuple[str, ...]:
        return tuple(n for n in PROVIDER_ENV[provider] if n not in self.configured_env)

    def reviewer_for(self, token: str) -> ReviewerToken | None:
        """Constant-time lookup over every configured token."""
        match: ReviewerToken | None = None
        for known, reviewer in self._reviewer_tokens.items():
            if hmac.compare_digest(known.encode(), token.encode()):
                match = reviewer
        return match


def _flag(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(name)
    if raw is None or raw == "":
        return default
    if raw not in {"0", "1"}:
        raise SettingsError(f"{name} must be 0 or 1")
    return raw == "1"


def _reviewer_tokens(env: Mapping[str, str]) -> dict[str, ReviewerToken]:
    """GAUNTLET_REVIEWER_TOKENS = JSON {token: {"reviewer_id": ..., "channel": ...}}."""
    raw = env.get("GAUNTLET_REVIEWER_TOKENS", "")
    if not raw:
        return {}
    try:
        table = json.loads(raw)
        tokens = {
            str(token): ReviewerToken(str(entry["reviewer_id"]), entry.get("channel", "dashboard"))
            for token, entry in table.items()
        }
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise SettingsError(
            "GAUNTLET_REVIEWER_TOKENS is not valid JSON of the documented shape"
        ) from exc
    for token, reviewer in tokens.items():
        if len(token) < 16:
            raise SettingsError("GAUNTLET_REVIEWER_TOKENS entries need tokens of 16+ characters")
        if reviewer.channel not in ("dashboard", "api"):
            raise SettingsError("GAUNTLET_REVIEWER_TOKENS channel must be dashboard or api")
    return tokens


def load_settings(env: Mapping[str, str] | None = None) -> ApiSettings:
    env = os.environ if env is None else env
    provider = env.get("GAUNTLET_MODEL_PROVIDER", "azure") or "azure"
    if provider not in ("azure", "bedrock"):
        raise SettingsError("GAUNTLET_MODEL_PROVIDER must be azure or bedrock")
    known = {name for names in PROVIDER_ENV.values() for name in names}
    return ApiSettings(
        run_live_integrations=_flag(env, "RUN_LIVE_INTEGRATIONS", False),
        model_provider=provider,  # type: ignore[arg-type]
        anchor_require_proxy=_flag(env, "GAUNTLET_ANCHOR_REQUIRE_PROXY", True),
        history_dir=Path(env.get("GAUNTLET_HISTORY_DIR") or REPO_ROOT / "apps/cartwheel/history"),
        refund_manifest=Path(
            env.get("GAUNTLET_REFUND_MANIFEST")
            or REPO_ROOT / "apps/cartwheel/refund-fixture-manifest.v1.json"
        ),
        configured_env=frozenset(n for n in known if env.get(n)),
        _reviewer_tokens=_reviewer_tokens(env),
    )


@lru_cache(maxsize=1)
def get_settings() -> ApiSettings:
    return load_settings()
