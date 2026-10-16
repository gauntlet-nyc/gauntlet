"""The one typed settings module. Every environment variable Gauntlet reads is declared here.

Rules:
- Values come only from the process environment (or a Mapping passed in tests).
- Errors and reports name variables, never values. Secrets are wrapped in `Secret`, whose
  repr/str are masked; call `.reveal()` only at the adapter boundary.
- Placeholder values from `.env.example` (containing `REPLACE_`) count as unset.
- An unset integration is `None`; `require(...)` raises `MissingSettingError("missing KEY")`.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Final, Literal
from urllib.parse import urlsplit

ModelProvider = Literal["azure", "bedrock"]


class SettingsError(ValueError):
    """Invalid configuration. The message names variables only."""


class MissingSettingError(SettingsError):
    def __init__(self, *names: str) -> None:
        self.names = names
        super().__init__("missing " + ", ".join(names))


class Secret:
    """A credential that never prints. Equality is deliberately identity-free of value leaks."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "Secret('***')"

    __str__ = __repr__

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Secret) and other._value == self._value

    def __hash__(self) -> int:
        return hash(("secret", self._value))


_PLACEHOLDER_MARKERS: Final = ("REPLACE_", "REPLACE-", "CHANGE_ME", "CHANGEME")


class _Env:
    def __init__(self, environ: Mapping[str, str]) -> None:
        self._environ = environ

    def get(self, name: str) -> str | None:
        raw = self._environ.get(name)
        if raw is None:
            return None
        value = raw.strip()
        if not value or any(marker in value.upper() for marker in _PLACEHOLDER_MARKERS):
            return None
        return value

    def flag(self, name: str, default: bool) -> bool:
        value = self.get(name)
        if value is None:
            return default
        lowered = value.lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
        raise SettingsError(f"{name} must be 0 or 1")

    def integer(self, name: str, default: int, *, minimum: int, maximum: int) -> int:
        value = self.get(name)
        if value is None:
            return default
        try:
            number = int(value)
        except ValueError:
            raise SettingsError(f"{name} must be an integer") from None
        if not minimum <= number <= maximum:
            raise SettingsError(f"{name} must be between {minimum} and {maximum}")
        return number

    def url(self, name: str, *, schemes: frozenset[str]) -> str | None:
        value = self.get(name)
        if value is None:
            return None
        try:
            parsed = urlsplit(value)
            parsed.port  # noqa: B018 - raises on a malformed port
        except ValueError:
            raise SettingsError(f"{name} is not a valid URL") from None
        if parsed.scheme not in schemes or not parsed.hostname or parsed.username:
            allowed = "/".join(sorted(schemes))
            raise SettingsError(f"{name} must be a {allowed} URL without userinfo")
        return value.rstrip("/")

    def secret(self, name: str) -> Secret | None:
        value = self.get(name)
        return None if value is None else Secret(value)


def _all_or_none(section: str, present: Mapping[str, object | None]) -> bool:
    """A section is configured when all its required keys are set; partial config is an error."""
    missing = [name for name, value in present.items() if value is None]
    if len(missing) == len(present):
        return False
    if missing:
        raise SettingsError(f"{section} is partially configured; missing {', '.join(missing)}")
    return True


@dataclass(frozen=True)
class CoreSettings:
    env: str
    log_level: str
    allowed_target_ids: frozenset[str]
    artifact_dir: Path
    max_concurrent_runs: int
    max_actions_per_attack: int
    max_run_seconds: int
    max_replay_attempts: int
    run_live_integrations: bool
    evidence_retention_days: int


@dataclass(frozen=True)
class AzureOpenAISettings:
    endpoint: str
    deployment: str
    api_key: Secret
    api_version: str
    reasoning_model: bool


@dataclass(frozen=True)
class BedrockSettings:
    region: str
    model_id: str
    profile: str | None


@dataclass(frozen=True)
class DaytonaSettings:
    api_key: Secret
    api_url: str
    target: str


@dataclass(frozen=True)
class AnchorProxySettings:
    server: str
    username: str
    password: Secret


@dataclass(frozen=True)
class AnchorSettings:
    api_key: Secret
    require_proxy: bool
    proxy: AnchorProxySettings | None


@dataclass(frozen=True)
class ArizeSettings:
    api_key: Secret
    space_id: Secret
    project_name: str
    otlp_endpoint: str


@dataclass(frozen=True)
class SurrealSettings:
    url: str
    namespace: str
    database: str
    user: str
    password: Secret


@dataclass(frozen=True)
class SurrealMemorySettings:
    endpoint: str
    context: str
    api_key: Secret


@dataclass(frozen=True)
class ElevenLabsSettings:
    api_key: Secret
    agent_id: str
    webhook_secret: Secret
    public_base_url: str | None


@dataclass(frozen=True)
class GitHubAppSettings:
    app_id: str
    installation_id: str
    private_key_path: Path
    webhook_secret: Secret
    api_url: str
    webhook_proxy_url: str | None


@dataclass(frozen=True)
class ReviewerSettings:
    """Dev-grade server-side reviewer tokens: `GAUNTLET_REVIEWER_TOKENS=name:token,...`."""

    tokens: tuple[tuple[str, Secret], ...]


DEFAULT_ARIZE_OTLP_ENDPOINT: Final = "https://otlp.arize.com/v1/traces"


@dataclass(frozen=True)
class Settings:
    core: CoreSettings
    model_provider: ModelProvider
    azure_openai: AzureOpenAISettings | None
    bedrock: BedrockSettings | None
    daytona: DaytonaSettings | None
    anchor: AnchorSettings | None
    arize: ArizeSettings | None
    surreal: SurrealSettings | None
    surreal_memory: SurrealMemorySettings | None
    elevenlabs: ElevenLabsSettings | None
    github_app: GitHubAppSettings | None
    reviewers: ReviewerSettings | None

    def readiness(self) -> dict[str, str]:
        """Names-only status for logs and `/health`-style reports; no values."""
        report: dict[str, str] = {}
        for item in fields(self):
            if item.name in {"core", "model_provider"}:
                continue
            report[item.name] = "configured" if getattr(self, item.name) is not None else "unset"
        report["model_provider"] = self.model_provider
        report["live_integrations"] = "enabled" if self.core.run_live_integrations else "disabled"
        if self.anchor is not None and not self.anchor.require_proxy:
            report["anchor"] = "configured_without_egress_proxy"
        return report


# The variables each section needs; used for "missing KEY" messages by `require`.
SECTION_KEYS: Final[dict[str, tuple[str, ...]]] = {
    "azure_openai": ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT", "AZURE_OPENAI_API_KEY"),
    "bedrock": ("AWS_REGION", "BEDROCK_MODEL_ID"),
    "daytona": ("DAYTONA_API_KEY", "DAYTONA_API_URL", "DAYTONA_TARGET"),
    "anchor": ("ANCHOR_API_KEY",),
    "arize": ("ARIZE_API_KEY", "ARIZE_SPACE_ID"),
    "surreal": ("SURREAL_URL", "SURREAL_NS", "SURREAL_DB", "SURREAL_USER", "SURREAL_PASS"),
    "surreal_memory": (
        "SURREAL_MEMORY_ENDPOINT",
        "SURREAL_MEMORY_CONTEXT",
        "SURREAL_MEMORY_API_KEY",
    ),
    "elevenlabs": ("ELEVENLABS_API_KEY", "ELEVENLABS_AGENT_ID", "VOICE_WEBHOOK_SECRET"),
    "github_app": (
        "GITHUB_APP_ID",
        "GITHUB_INSTALLATION_ID",
        "GITHUB_PRIVATE_KEY_PATH",
        "GITHUB_WEBHOOK_SECRET",
    ),
    "reviewers": ("GAUNTLET_REVIEWER_TOKENS",),
}


def require[T](section: str, value: T | None) -> T:
    """Return a configured section or raise `missing KEY_NAME, ...` for that section."""
    if value is None:
        raise MissingSettingError(*SECTION_KEYS[section])
    return value


def _load_anchor(env: _Env) -> AnchorSettings | None:
    api_key = env.secret("ANCHOR_API_KEY")
    require_proxy = env.flag("GAUNTLET_ANCHOR_REQUIRE_PROXY", True)
    server = env.url("ANCHOR_PROXY_SERVER", schemes=frozenset({"http", "https"}))
    username = env.get("ANCHOR_PROXY_USERNAME")
    password = env.secret("ANCHOR_PROXY_PASSWORD")
    proxy_present = _all_or_none(
        "Anchor proxy",
        {
            "ANCHOR_PROXY_SERVER": server,
            "ANCHOR_PROXY_USERNAME": username,
            "ANCHOR_PROXY_PASSWORD": password,
        },
    )
    if api_key is None:
        return None
    if require_proxy and not proxy_present:
        raise MissingSettingError(
            "ANCHOR_PROXY_SERVER",
            "ANCHOR_PROXY_USERNAME",
            "ANCHOR_PROXY_PASSWORD (or set GAUNTLET_ANCHOR_REQUIRE_PROXY=0)",
        )
    proxy = None
    if proxy_present:
        assert server is not None and username is not None and password is not None
        proxy = AnchorProxySettings(server=server, username=username, password=password)
    return AnchorSettings(api_key=api_key, require_proxy=require_proxy, proxy=proxy)


def _load_reviewers(env: _Env) -> ReviewerSettings | None:
    raw = env.get("GAUNTLET_REVIEWER_TOKENS")
    if raw is None:
        return None
    tokens: list[tuple[str, Secret]] = []
    for entry in raw.split(","):
        name, sep, token = entry.strip().partition(":")
        if not sep or not name or len(token) < 16:
            raise SettingsError(
                "GAUNTLET_REVIEWER_TOKENS must be name:token pairs with tokens of 16+ characters"
            )
        tokens.append((name, Secret(token)))
    return ReviewerSettings(tokens=tuple(tokens))


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    """Validate every variable once. Raises `SettingsError` naming the bad variables."""
    env = _Env(os.environ if environ is None else environ)
    core = CoreSettings(
        env=env.get("GAUNTLET_ENV") or "local",
        log_level=(env.get("GAUNTLET_LOG_LEVEL") or "INFO").upper(),
        allowed_target_ids=frozenset(
            item.strip()
            for item in (env.get("GAUNTLET_ALLOWED_TARGET_IDS") or "").split(",")
            if item.strip()
        ),
        artifact_dir=Path(env.get("GAUNTLET_ARTIFACT_DIR") or "./artifacts"),
        max_concurrent_runs=env.integer("GAUNTLET_MAX_CONCURRENT_RUNS", 2, minimum=1, maximum=64),
        max_actions_per_attack=env.integer(
            "GAUNTLET_MAX_ACTIONS_PER_ATTACK", 50, minimum=1, maximum=500
        ),
        max_run_seconds=env.integer("GAUNTLET_MAX_RUN_SECONDS", 900, minimum=10, maximum=7200),
        max_replay_attempts=env.integer("GAUNTLET_MAX_REPLAY_ATTEMPTS", 3, minimum=1, maximum=10),
        run_live_integrations=env.flag("RUN_LIVE_INTEGRATIONS", False),
        evidence_retention_days=env.integer(
            "GAUNTLET_EVIDENCE_RETENTION_DAYS", 30, minimum=1, maximum=3650
        ),
    )
    if core.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
        raise SettingsError("GAUNTLET_LOG_LEVEL must be DEBUG, INFO, WARNING or ERROR")

    provider = (env.get("GAUNTLET_MODEL_PROVIDER") or "azure").lower()
    if provider not in {"azure", "bedrock"}:
        raise SettingsError("GAUNTLET_MODEL_PROVIDER must be azure or bedrock")

    azure = None
    azure_values = {
        "AZURE_OPENAI_ENDPOINT": env.url("AZURE_OPENAI_ENDPOINT", schemes=frozenset({"https"})),
        "AZURE_OPENAI_DEPLOYMENT": env.get("AZURE_OPENAI_DEPLOYMENT"),
        "AZURE_OPENAI_API_KEY": env.secret("AZURE_OPENAI_API_KEY"),
    }
    if _all_or_none("Azure OpenAI", azure_values):
        azure = AzureOpenAISettings(
            endpoint=str(azure_values["AZURE_OPENAI_ENDPOINT"]),
            deployment=str(azure_values["AZURE_OPENAI_DEPLOYMENT"]),
            api_key=env.secret("AZURE_OPENAI_API_KEY") or Secret(""),
            api_version=env.get("AZURE_OPENAI_API_VERSION") or "2024-10-21",
            reasoning_model=env.flag("AZURE_OPENAI_REASONING_MODEL", False),
        )

    bedrock = None
    region, model_id = env.get("AWS_REGION"), env.get("BEDROCK_MODEL_ID")
    if model_id is not None:
        if region is None:
            raise MissingSettingError("AWS_REGION")
        bedrock = BedrockSettings(region=region, model_id=model_id, profile=env.get("AWS_PROFILE"))

    daytona = None
    daytona_values = {
        "DAYTONA_API_KEY": env.secret("DAYTONA_API_KEY"),
        "DAYTONA_API_URL": env.url("DAYTONA_API_URL", schemes=frozenset({"https"})),
        "DAYTONA_TARGET": env.get("DAYTONA_TARGET"),
    }
    if _all_or_none("Daytona", daytona_values):
        daytona = DaytonaSettings(
            api_key=env.secret("DAYTONA_API_KEY") or Secret(""),
            api_url=str(daytona_values["DAYTONA_API_URL"]),
            target=str(daytona_values["DAYTONA_TARGET"]),
        )

    arize = None
    arize_values = {
        "ARIZE_API_KEY": env.secret("ARIZE_API_KEY"),
        "ARIZE_SPACE_ID": env.secret("ARIZE_SPACE_ID"),
    }
    if _all_or_none("Arize", arize_values):
        arize = ArizeSettings(
            api_key=env.secret("ARIZE_API_KEY") or Secret(""),
            space_id=env.secret("ARIZE_SPACE_ID") or Secret(""),
            project_name=env.get("ARIZE_PROJECT_NAME") or "gauntlet",
            otlp_endpoint=env.url("ARIZE_OTLP_ENDPOINT", schemes=frozenset({"https"}))
            or DEFAULT_ARIZE_OTLP_ENDPOINT,
        )

    surreal = None
    surreal_values = {
        "SURREAL_URL": env.url("SURREAL_URL", schemes=frozenset({"http", "https", "ws", "wss"})),
        "SURREAL_NS": env.get("SURREAL_NS"),
        "SURREAL_DB": env.get("SURREAL_DB"),
        "SURREAL_USER": env.get("SURREAL_USER"),
        "SURREAL_PASS": env.secret("SURREAL_PASS"),
    }
    # URL/NS/DB/USER have harmless defaults in .env.example; the password decides.
    if surreal_values["SURREAL_PASS"] is not None and _all_or_none("SurrealDB", surreal_values):
        surreal = SurrealSettings(
            url=str(surreal_values["SURREAL_URL"]),
            namespace=str(surreal_values["SURREAL_NS"]),
            database=str(surreal_values["SURREAL_DB"]),
            user=str(surreal_values["SURREAL_USER"]),
            password=env.secret("SURREAL_PASS") or Secret(""),
        )

    memory = None
    memory_values = {
        "SURREAL_MEMORY_ENDPOINT": env.url(
            "SURREAL_MEMORY_ENDPOINT", schemes=frozenset({"http", "https"})
        ),
        "SURREAL_MEMORY_API_KEY": env.secret("SURREAL_MEMORY_API_KEY"),
    }
    if _all_or_none("SurrealDB Agent Memory", memory_values):
        memory = SurrealMemorySettings(
            endpoint=str(memory_values["SURREAL_MEMORY_ENDPOINT"]),
            context=env.get("SURREAL_MEMORY_CONTEXT") or "gauntlet-dev",
            api_key=env.secret("SURREAL_MEMORY_API_KEY") or Secret(""),
        )

    elevenlabs = None
    eleven_values = {
        "ELEVENLABS_API_KEY": env.secret("ELEVENLABS_API_KEY"),
        "ELEVENLABS_AGENT_ID": env.get("ELEVENLABS_AGENT_ID"),
        "VOICE_WEBHOOK_SECRET": env.secret("VOICE_WEBHOOK_SECRET"),
    }
    if _all_or_none("ElevenLabs", eleven_values):
        elevenlabs = ElevenLabsSettings(
            api_key=env.secret("ELEVENLABS_API_KEY") or Secret(""),
            agent_id=str(eleven_values["ELEVENLABS_AGENT_ID"]),
            webhook_secret=env.secret("VOICE_WEBHOOK_SECRET") or Secret(""),
            public_base_url=env.url("PUBLIC_BASE_URL", schemes=frozenset({"https"})),
        )

    github = None
    github_values = {
        "GITHUB_APP_ID": env.get("GITHUB_APP_ID"),
        "GITHUB_INSTALLATION_ID": env.get("GITHUB_INSTALLATION_ID"),
        "GITHUB_PRIVATE_KEY_PATH": env.get("GITHUB_PRIVATE_KEY_PATH"),
        "GITHUB_WEBHOOK_SECRET": env.secret("GITHUB_WEBHOOK_SECRET"),
    }
    if _all_or_none("GitHub App", github_values):
        for name in ("GITHUB_APP_ID", "GITHUB_INSTALLATION_ID"):
            if not str(github_values[name]).isdigit():
                raise SettingsError(f"{name} must be numeric")
        github = GitHubAppSettings(
            app_id=str(github_values["GITHUB_APP_ID"]),
            installation_id=str(github_values["GITHUB_INSTALLATION_ID"]),
            private_key_path=Path(str(github_values["GITHUB_PRIVATE_KEY_PATH"])),
            webhook_secret=env.secret("GITHUB_WEBHOOK_SECRET") or Secret(""),
            api_url=env.url("GITHUB_API_URL", schemes=frozenset({"https"}))
            or "https://api.github.com",
            webhook_proxy_url=env.url("GITHUB_WEBHOOK_PROXY_URL", schemes=frozenset({"https"})),
        )

    settings = Settings(
        core=core,
        model_provider="bedrock" if provider == "bedrock" else "azure",
        azure_openai=azure,
        bedrock=bedrock,
        daytona=daytona,
        anchor=_load_anchor(env),
        arize=arize,
        surreal=surreal,
        surreal_memory=memory,
        elevenlabs=elevenlabs,
        github_app=github,
        reviewers=_load_reviewers(env),
    )
    return settings


def require_live(settings: Settings) -> None:
    if not settings.core.run_live_integrations:
        raise MissingSettingError("RUN_LIVE_INTEGRATIONS=1")
