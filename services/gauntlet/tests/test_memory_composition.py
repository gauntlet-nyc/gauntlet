"""Composition must select the configured memory protocol before any provider call."""

import sys
from types import ModuleType

import pytest

from gauntlet.composition import build_memory
from gauntlet.memory.agent_memory_sdk import AgentMemorySdkStore
from gauntlet.memory.surreal_memory import SurrealTemporalMemory
from gauntlet.settings import MissingSettingError, Settings

ENV = {
    "RUN_LIVE_INTEGRATIONS": "1",
    "SURREAL_MEMORY_ENDPOINT": "https://memory.example",
    "SURREAL_MEMORY_CONTEXT": "test-context",
    "SURREAL_MEMORY_API_KEY": "synthetic-memory-key",
}


@pytest.mark.parametrize("backend", ["sdk", "http", "auto"])
def test_build_memory_selects_configured_backend(
    monkeypatch: pytest.MonkeyPatch, backend: str
) -> None:
    class OfflineSdkClient:
        def __init__(self, context: str, *, endpoint: str, api_key: str) -> None:
            assert (context, endpoint, api_key) == (
                ENV["SURREAL_MEMORY_CONTEXT"],
                ENV["SURREAL_MEMORY_ENDPOINT"],
                ENV["SURREAL_MEMORY_API_KEY"],
            )

    sdk = ModuleType("surrealdb.memory")
    sdk.AsyncMemory = OfflineSdkClient  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "surrealdb.memory", sdk)
    # Typed settings are authoritative even if a caller supplied an explicit mapping.
    monkeypatch.setenv("GAUNTLET_MEMORY_BACKEND", "http")
    settings = Settings.from_env({**ENV, "GAUNTLET_MEMORY_BACKEND": backend})
    store, label = build_memory("surreal", settings)
    expected = SurrealTemporalMemory if backend == "http" else AgentMemorySdkStore
    assert isinstance(store, expected)
    assert label == "live_surreal_memory"


def test_build_memory_still_requires_live_opt_in() -> None:
    with pytest.raises(MissingSettingError, match="RUN_LIVE_INTEGRATIONS"):
        build_memory("surreal", Settings.from_env({**ENV, "RUN_LIVE_INTEGRATIONS": "0"}))
