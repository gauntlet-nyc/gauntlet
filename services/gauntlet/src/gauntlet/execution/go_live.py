"""Morning go-live check: which sponsors are configured, and (with --probe) does ONE cheap,
bounded call per configured provider actually succeed.

Reports variable NAMES only, never values. Failure reasons are sanitized: our own adapter
messages (which never contain credentials) are kept; anything else is reduced to the
exception type, and every configured secret value is scrubbed as a second guard. Every
probe that creates something (only Anchor: one session) deletes it in `finally`.
"""

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, fields
from datetime import UTC, datetime
from typing import Final, Literal

from gauntlet.ports.errors import PortError
from gauntlet.settings import IntegrationSettings, Secret, SettingsError

Status = Literal["ready", "missing", "probe_ok", "probe_failed", "not_probed"]
Probe = Callable[[IntegrationSettings], Awaitable[str]]

PROBE_TIMEOUT_SECONDS: Final = 25.0

# Sponsor -> (settings section, variable names required).
SPONSORS: Final[dict[str, tuple[str, tuple[str, ...]]]] = {
    "azure_openai": (
        "azure_openai",
        ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT", "AZURE_OPENAI_API_KEY"),
    ),
    "daytona": ("daytona", ("DAYTONA_API_KEY", "DAYTONA_TARGET")),
    "anchor": ("anchor", ("ANCHOR_API_KEY",)),
    "arize": ("arize", ("ARIZE_API_KEY", "ARIZE_SPACE_ID")),
    "surrealdb": ("surreal", ("SURREAL_URL", "SURREAL_NS", "SURREAL_DB", "SURREAL_USER",
                              "SURREAL_PASS")),
    "surrealdb_memory": ("surreal_memory", ("SURREAL_MEMORY_ENDPOINT",
                                            "SURREAL_MEMORY_API_KEY")),
    "elevenlabs": ("elevenlabs", ("ELEVENLABS_API_KEY", "ELEVENLABS_AGENT_ID",
                                  "VOICE_WEBHOOK_SECRET")),
    "github_app": ("github_app", ("GITHUB_APP_ID", "GITHUB_INSTALLATION_ID",
                                  "GITHUB_PRIVATE_KEY_PATH", "GITHUB_WEBHOOK_SECRET")),
}  # fmt: skip


@dataclass(frozen=True)
class SponsorResult:
    sponsor: str
    status: Status
    detail: str = ""

    def line(self) -> str:
        label = {
            "ready": "ready",
            "missing": f"missing: {self.detail}",
            "probe_ok": f"probe ok ({self.detail})" if self.detail else "probe ok",
            "probe_failed": f"probe failed: {self.detail}",
            "not_probed": f"not probed: {self.detail}",
        }[self.status]
        return f"{self.sponsor:<18} {label}"


def missing_names(environ: Mapping[str, str], names: tuple[str, ...]) -> list[str]:
    from gauntlet.settings import _read  # same placeholder rules as the settings module

    return [name for name in names if _read(environ, name) is None]


def _secrets(settings: IntegrationSettings) -> list[str]:
    values: list[str] = []

    def walk(item: object) -> None:
        if isinstance(item, Secret):
            values.append(item.reveal())
        elif hasattr(item, "__dataclass_fields__"):
            for field in fields(item):  # type: ignore[arg-type]
                walk(getattr(item, field.name))
        elif isinstance(item, tuple):
            for entry in item:
                walk(entry)

    walk(settings)
    return [value for value in values if len(value) >= 4]


def sanitize(exc: BaseException, secrets: list[str]) -> str:
    if isinstance(exc, (PortError, SettingsError, TimeoutError)):
        text = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
    else:
        text = type(exc).__name__
    for secret in secrets:
        text = text.replace(secret, "***")
    return text[:200]


async def run_check(
    environ: Mapping[str, str],
    settings: IntegrationSettings,
    *,
    probe: bool,
    probes: Mapping[str, Probe],
    timeout_seconds: float = PROBE_TIMEOUT_SECONDS,
) -> list[SponsorResult]:
    results: list[SponsorResult] = []
    secrets = _secrets(settings)
    for sponsor, (section, names) in SPONSORS.items():
        configured = getattr(settings, section) is not None
        if not configured:
            missing = missing_names(environ, names) or list(names)
            results.append(SponsorResult(sponsor, "missing", ", ".join(missing)))
            continue
        if not probe:
            results.append(SponsorResult(sponsor, "ready"))
            continue
        if not settings.core.run_live_integrations:
            results.append(SponsorResult(sponsor, "not_probed", "set RUN_LIVE_INTEGRATIONS=1"))
            continue
        handler = probes.get(sponsor)
        if handler is None:
            results.append(SponsorResult(sponsor, "not_probed", "no probe"))
            continue
        try:
            detail = await asyncio.wait_for(handler(settings), timeout_seconds)
        except Exception as exc:  # noqa: BLE001 - every failure becomes a sanitized row
            results.append(SponsorResult(sponsor, "probe_failed", sanitize(exc, secrets)))
        else:
            results.append(SponsorResult(sponsor, "probe_ok", detail))
    return results


def exit_code(results: list[SponsorResult]) -> int:
    return 1 if any(item.status == "probe_failed" for item in results) else 0


def render(results: list[SponsorResult], *, probed: bool) -> str:
    header = f"Gauntlet go-live check ({datetime.now(UTC):%Y-%m-%d %H:%M} UTC, "
    header += "live probes" if probed else "configuration only"
    return "\n".join([header + ")", *(item.line() for item in results)])
