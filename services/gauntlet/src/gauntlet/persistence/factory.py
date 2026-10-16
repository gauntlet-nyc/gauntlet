"""Build SurrealDB clients from typed settings. Missing settings -> `missing KEY` errors."""

from typing import TYPE_CHECKING

from gauntlet.ports.errors import EnvironmentUnavailableError
from gauntlet.settings import IntegrationSettings, require

from .surreal_client import SurrealHttpClient

if TYPE_CHECKING:
    from gauntlet.memory.agent_memory_sdk import AgentMemorySdkStore
    from gauntlet.memory.surreal_memory import SurrealTemporalMemory


def core_client(settings: IntegrationSettings) -> SurrealHttpClient:
    config = require("surreal", settings.surreal)
    return SurrealHttpClient(
        url=config.url,
        namespace=config.namespace,
        database=config.database,
        user=config.user,
        password=config.password.reveal(),
    )


def memory_client(settings: IntegrationSettings) -> SurrealHttpClient:
    """The memory context is a separate endpoint/database with its own token."""
    from gauntlet.memory.surreal_memory import MEMORY_NAMESPACE

    config = require("surreal_memory", settings.surreal_memory)
    return SurrealHttpClient(
        url=config.endpoint,
        namespace=MEMORY_NAMESPACE,
        database=config.context,
        token=config.api_key.reveal(),
    )


def memory_store(
    settings: IntegrationSettings, *, backend: str | None = None
) -> "AgentMemorySdkStore | SurrealTemporalMemory":
    """Agent Memory SDK adapter when installed (preferred), else the HTTP memory context.

    `backend` (or `GAUNTLET_MEMORY_BACKEND`): `sdk`, `http`, or unset for auto. Both
    returned objects implement `MemoryReader` and `MemoryWriter`.
    """
    import os

    from gauntlet.memory.agent_memory_sdk import AgentMemorySdkStore
    from gauntlet.memory.surreal_memory import SurrealTemporalMemory

    choice = (backend or os.environ.get("GAUNTLET_MEMORY_BACKEND") or "auto").lower()
    if choice not in {"auto", "sdk", "http"}:
        raise ValueError("GAUNTLET_MEMORY_BACKEND must be sdk, http or unset")
    config = require("surreal_memory", settings.surreal_memory)
    if choice != "http":
        try:
            from surrealdb.memory import AsyncMemory
        except ImportError:
            if choice == "sdk":
                raise EnvironmentUnavailableError(
                    "missing surrealdb[memory] SDK (live-providers group)"
                ) from None
        else:
            return AgentMemorySdkStore(
                AsyncMemory(
                    config.context, endpoint=config.endpoint, api_key=config.api_key.reveal()
                )
            )
    return SurrealTemporalMemory(memory_client(settings))
