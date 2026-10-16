"""The one typed settings module. Every setting and key is read from environment variables here.

Rules: secrets are wrapped so they never print; a missing key raises ``MissingSettingError``
naming only the variable (never a value); callers choose a labeled offline fallback instead of
silently mocking a live provider.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Literal, get_args

ModelProvider = Literal["scripted", "azure", "bedrock"]
SandboxKind = Literal["fake", "local", "daytona"]
BrowserKind = Literal["fake", "local", "anchor"]

_TRUE: Final = frozenset({"1", "true", "yes", "on"})
_FALSE: Final = frozenset({"0", "false", "no", "off", ""})


class MissingSettingError(RuntimeError):
    """A required environment variable is unset. The message names the variable only."""

    def __init__(self, name: str) -> None:
        super().__init__(f"missing {name}")
        self.name = name


class InvalidSettingError(ValueError):
    def __init__(self, name: str, expected: str) -> None:
        super().__init__(f"invalid {name}: expected {expected}")
        self.name = name


@dataclass(frozen=True)
class Secret:
    """Opaque secret value. ``str()``/``repr()`` never reveal it; call ``reveal()`` at use."""

    _value: str = field(repr=False)

    def reveal(self) -> str:
        return self._value

    def __str__(self) -> str:
        return "Secret(**********)"

    __repr__ = __str__


def _read(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name)
    if value is None:
        return None
    value = value.strip()
    # Template placeholders from .env.example count as unset.
    if not value or value.startswith("REPLACE"):
        return None
    return value


def _flag(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(name)
    if raw is None:
        return default
    lowered = raw.strip().lower()
    if lowered in _TRUE:
        return True
    if lowered in _FALSE:
        return False
    raise InvalidSettingError(name, "0 or 1")


def _choice[T: str](env: Mapping[str, str], name: str, options: tuple[T, ...], default: T) -> T:
    raw = _read(env, name)
    if raw is None:
        return default
    for option in options:
        if raw == option:
            return option
    raise InvalidSettingError(name, " | ".join(options))


def _int(env: Mapping[str, str], name: str, default: int, *, low: int, high: int) -> int:
    raw = _read(env, name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise InvalidSettingError(name, f"integer {low}..{high}") from None
    if not low <= value <= high:
        raise InvalidSettingError(name, f"integer {low}..{high}")
    return value


@dataclass(frozen=True)
class Settings:
    env: Mapping[str, str] = field(repr=False)
    model_provider: ModelProvider
    run_live_integrations: bool
    artifact_dir: Path
    max_run_seconds: int
    anchor_require_proxy: bool

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        source = dict(os.environ if env is None else env)
        return cls(
            env=source,
            model_provider=_choice(
                source, "GAUNTLET_MODEL_PROVIDER", get_args(ModelProvider), "scripted"
            ),
            run_live_integrations=_flag(source, "RUN_LIVE_INTEGRATIONS", False),
            artifact_dir=Path(_read(source, "GAUNTLET_ARTIFACT_DIR") or "./artifacts"),
            max_run_seconds=_int(source, "GAUNTLET_MAX_RUN_SECONDS", 1800, low=60, high=7200),
            # Default is the safer setting; the demo sets 0 explicitly (weaker isolation).
            anchor_require_proxy=_flag(source, "GAUNTLET_ANCHOR_REQUIRE_PROXY", True),
        )

    # -- plain values ------------------------------------------------------------------------

    def optional(self, name: str) -> str | None:
        return _read(self.env, name)

    def require(self, name: str) -> str:
        value = _read(self.env, name)
        if value is None:
            raise MissingSettingError(name)
        return value

    def secret(self, name: str) -> Secret:
        return Secret(self.require(name))

    def flag(self, name: str, default: bool = False) -> bool:
        return _flag(self.env, name, default)

    def missing(self, *names: str) -> tuple[str, ...]:
        """Names of unset variables, for a readiness report. Never returns values."""
        return tuple(name for name in names if _read(self.env, name) is None)

    def require_live(self, provider: str) -> None:
        if not self.run_live_integrations:
            raise MissingSettingError(f"RUN_LIVE_INTEGRATIONS=1 (required for live {provider})")


AZURE_KEYS: Final = ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT", "AZURE_OPENAI_API_KEY")
BEDROCK_KEYS: Final = ("BEDROCK_MODEL_ID", "AWS_REGION")
DAYTONA_KEYS: Final = ("DAYTONA_API_KEY", "DAYTONA_TARGET")
ANCHOR_KEYS: Final = ("ANCHOR_API_KEY",)
ANCHOR_PROXY_KEYS: Final = ("ANCHOR_PROXY_SERVER", "ANCHOR_PROXY_USERNAME", "ANCHOR_PROXY_PASSWORD")
LOCAL_ORIGIN_KEYS: Final = ("CARTWHEEL_BASE_ORIGIN", "CARTWHEEL_HEAD_ORIGIN")
