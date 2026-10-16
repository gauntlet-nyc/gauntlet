"""One cheap, bounded live call per sponsor for `scripts/go_live_check.py`.

Each probe reads only typed settings, makes the smallest call that proves the key and
endpoint work, and closes what it opened. Only the Anchor probe creates a resource (one
browser session); it is deleted in `finally`, and a failed delete is reported with the
session ID so it can be cleaned up by hand.
"""

from typing import Any, Final

from gauntlet.integrations.arize.tracing import OtlpTracer
from gauntlet.integrations.azure_openai import AzureOpenAIGateway
from gauntlet.integrations.elevenlabs import ElevenLabsVoice
from gauntlet.integrations.github_app import GitHubAppCheckRunPublisher
from gauntlet.persistence.factory import core_client, memory_client
from gauntlet.ports.errors import EnvironmentUnavailableError
from gauntlet.ports.model import ModelRequest
from gauntlet.settings import IntegrationSettings, require

from .go_live import Probe


async def probe_azure(settings: IntegrationSettings) -> str:
    config = require("azure_openai", settings.azure_openai)
    gateway = AzureOpenAIGateway(
        endpoint=config.endpoint,
        deployment=config.deployment,
        api_key=config.api_key.reveal(),
        api_version=config.api_version,
        reasoning_model=config.reasoning_model,
    )
    response = await gateway.complete(
        ModelRequest(system="Reply with the single word OK.", user="OK", max_output_tokens=16)
    )
    return f"model {response.model_id} replied"


async def probe_daytona(settings: IntegrationSettings) -> str:
    config = require("daytona", settings.daytona)
    try:
        from daytona import AsyncDaytona, DaytonaConfig
    except ImportError:
        raise EnvironmentUnavailableError("missing daytona SDK (live-providers group)") from None
    client = AsyncDaytona(
        DaytonaConfig(api_key=config.api_key.reveal(), api_url=config.api_url, target=config.target)
    )
    try:
        page = await client.snapshot.list(page=1, limit=1)  # read-only, nothing created
    finally:
        await client.close()  # type: ignore[no-untyped-call]
    total = getattr(page, "total", None)
    return f"{total} snapshots visible" if isinstance(total, int) else "snapshots listed"


async def probe_anchor(settings: IntegrationSettings) -> str:
    config = require("anchor", settings.anchor)
    try:
        from anchorbrowser import AsyncAnchorbrowser
    except ImportError:
        raise EnvironmentUnavailableError(
            "missing anchorbrowser SDK (live-providers group)"
        ) from None
    session: dict[str, Any] = {"recording": {"active": False}}
    if config.proxy is not None:
        session["proxy"] = {
            "type": "custom",
            "server": config.proxy.server,
            "username": config.proxy.username,
            "password": config.proxy.password.reveal(),
            "active": True,
        }
    client = AsyncAnchorbrowser(api_key=config.api_key.reveal(), max_retries=0, timeout=30)
    session_id: str | None = None
    try:
        created = await client.sessions.create_session(
            session=session,  # type: ignore[arg-type]  # SDK TypedDict, same keys as sdk.py
            browser={"headless": {"active": True}},
            timeout=30,
        )
        session_id = getattr(getattr(created, "data", None), "id", None)
        if not isinstance(session_id, str) or not session_id:
            raise EnvironmentUnavailableError("Anchor returned no session ID")
    finally:
        if isinstance(session_id, str) and session_id:
            try:
                await client.sessions.delete_session(session_id, timeout=15)
            except Exception:
                await client.close()
                raise EnvironmentUnavailableError(
                    f"Anchor session {session_id} was created but NOT deleted; delete it by hand"
                ) from None
        await client.close()
    isolation = "with egress proxy" if config.proxy else "WITHOUT egress proxy"
    return f"session created and deleted ({isolation})"


async def probe_arize(settings: IntegrationSettings) -> str:
    config = require("arize", settings.arize)
    tracer = OtlpTracer(
        endpoint=config.otlp_endpoint,
        headers={"space_id": config.space_id.reveal(), "api_key": config.api_key.reveal()},
        project_name=config.project_name,
    )
    async with tracer.span("go_live.probe", "CHAIN", {"gauntlet.probe": True}) as span:
        trace_id = span.trace_id
    await tracer.flush()
    if tracer.exported != 1:
        raise EnvironmentUnavailableError("Arize did not accept the span (see logged HTTP code)")
    return f"span exported, trace {trace_id}"


async def _surreal_round_trip(client_factory: str, settings: IntegrationSettings) -> str:
    client = core_client(settings) if client_factory == "core" else memory_client(settings)
    try:
        result = await client.query("RETURN 1;")
    finally:
        await client.close()
    if not result or result[0].result != 1:
        raise EnvironmentUnavailableError("SurrealDB returned an unexpected result")
    return "connected, RETURN 1 ok"


async def probe_surreal(settings: IntegrationSettings) -> str:
    return await _surreal_round_trip("core", settings)


async def probe_surreal_memory(settings: IntegrationSettings) -> str:
    return await _surreal_round_trip("memory", settings) + " (HTTP memory context)"


async def probe_elevenlabs(settings: IntegrationSettings) -> str:
    await ElevenLabsVoice.from_settings(settings).check_auth()
    return "API key accepted"


async def probe_github(settings: IntegrationSettings) -> str:
    await GitHubAppCheckRunPublisher.from_settings(settings).check_installation()
    return "installation token minted (checks: write)"


PROBES: Final[dict[str, Probe]] = {
    "azure_openai": probe_azure,
    "daytona": probe_daytona,
    "anchor": probe_anchor,
    "arize": probe_arize,
    "surrealdb": probe_surreal,
    "surrealdb_memory": probe_surreal_memory,
    "elevenlabs": probe_elevenlabs,
    "github_app": probe_github,
}
