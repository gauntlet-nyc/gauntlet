"""Build SurrealDB clients from typed settings. Missing settings -> `missing KEY` errors."""

from gauntlet.settings import IntegrationSettings, require

from .surreal_client import SurrealHttpClient


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
