"""One cheap, bounded live call per sponsor for `scripts/go_live_check.py`.

Each probe reads only typed settings, makes the smallest call that proves the key and
endpoint work, and closes what it opened. Only the Anchor probe creates a resource (one
browser session); it is deleted in `finally`, and a failed delete is reported with the
session ID so it can be cleaned up by hand.
"""

import asyncio
from collections.abc import Coroutine
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
        ModelRequest(
            system="Reply with the JSON object {\"ok\": true}.",
            user="Return the json now.",
            # Reasoning deployments spend tokens before answering.
            max_output_tokens=1024,
        )
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


ANCHOR_CREATE_TIMEOUT_SECONDS = 35.0
ANCHOR_DELETE_TIMEOUT_SECONDS = 20.0
ANCHOR_CLOSE_TIMEOUT_SECONDS = 5.0


async def _settle[T](operation: Coroutine[Any, Any, T], timeout: float) -> tuple[T, bool]:
    """Keep cancellation from abandoning a resource operation; never extend its deadline."""
    task = asyncio.create_task(operation)
    deadline = asyncio.get_running_loop().time() + timeout
    cancelled = False
    try:
        while True:
            remaining = max(0.0, deadline - asyncio.get_running_loop().time())
            try:
                return await asyncio.wait_for(asyncio.shield(task), remaining), cancelled
            except asyncio.CancelledError:
                if task.cancelled():
                    raise
                cancelled = True
    finally:
        if not task.done():
            task.cancel()
            # SDK calls are bounded and cancellation-cooperative. Observe the terminal
            # exception so no abandoned request task outlives the probe.
            await asyncio.gather(task, return_exceptions=True)


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
    cancelled = False
    cleanup_error: EnvironmentUnavailableError | None = None
    try:
        try:
            created, interrupted = await _settle(
                client.sessions.create_session(
                    session=session,  # type: ignore[arg-type]
                    browser={"headless": {"active": True}},
                    timeout=30,
                ),
                ANCHOR_CREATE_TIMEOUT_SECONDS,
            )
            cancelled |= interrupted
        except TimeoutError:
            raise EnvironmentUnavailableError(
                "Anchor creation timed out; session outcome unknown; check provider resources"
            ) from None
        session_id = getattr(getattr(created, "data", None), "id", None)
        if not isinstance(session_id, str) or not session_id:
            raise EnvironmentUnavailableError("Anchor returned no session ID")
    finally:
        try:
            if isinstance(session_id, str) and session_id:
                try:
                    _, interrupted = await _settle(
                        client.sessions.delete_session(session_id, timeout=15),
                        ANCHOR_DELETE_TIMEOUT_SECONDS,
                    )
                    cancelled |= interrupted
                except Exception:
                    cleanup_error = EnvironmentUnavailableError(
                        f"Anchor session {session_id} was created but NOT deleted; "
                        "delete it by hand"
                    )
        finally:
            try:
                _, interrupted = await _settle(client.close(), ANCHOR_CLOSE_TIMEOUT_SECONDS)
                cancelled |= interrupted
            except Exception:
                if cleanup_error is None:
                    cleanup_error = EnvironmentUnavailableError("Anchor client close failed")
        if cleanup_error is not None:
            raise cleanup_error from None
    if cancelled:
        raise asyncio.CancelledError
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
    """Agent Memory SDK `whoami` when the SDK is installed, else the HTTP memory context."""
    config = require("surreal_memory", settings.surreal_memory)
    try:
        from surrealdb.memory import AsyncMemory
    except ImportError:
        return await _surreal_round_trip("memory", settings) + " (HTTP memory context)"
    client = AsyncMemory(config.context, endpoint=config.endpoint, api_key=config.api_key.reveal())
    try:
        principal = await client.whoami()
    finally:
        await client.close()
    return f"Agent Memory SDK authenticated as {getattr(principal, 'kind', 'principal')}"


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
