"""Agent Memory SDK adapter: encoding, as-of/supersession, and the real SDK request path
with an injected fake transport (no network). SDK tests skip without live-providers."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from gauntlet.contracts import MemoryProvenance, TemporalMemoryFact
from gauntlet.memory.agent_memory_sdk import (
    AgentMemorySdkStore,
    decode_fact_text,
    encode_fact_text,
)
from gauntlet.memory.surreal_memory import SurrealTemporalMemory
from gauntlet.persistence.factory import memory_store
from gauntlet.ports.errors import EnvironmentUnavailableError
from gauntlet.ports.memory import MemoryQuery
from gauntlet.settings import load_settings

T0 = datetime(2026, 10, 1, tzinfo=UTC)
MEMORY_ENV = {
    "SURREAL_MEMORY_ENDPOINT": "https://memory.example",
    "SURREAL_MEMORY_API_KEY": "k" * 20,
}


def _fact(
    fact_id: str, known: datetime, supersedes: str | None = None, kind: str = "ui_occlusion"
) -> TemporalMemoryFact:
    return TemporalMemoryFact(
        fact_id=fact_id,
        kind=kind,  # type: ignore[arg-type]
        summary="Floating help overlaps checkout on narrow viewports",
        verification="confirmed",
        trust="verified_test",
        scope="cartwheel",
        surface_kinds=("component", "style"),
        source=MemoryProvenance(finding_id="finding-1", oracle_id="ui.primary_action_reachable"),
        known_at=known,
        valid_from=known,
        supersedes=supersedes,
    )


def _query(as_of: datetime, lens: str = "planner") -> MemoryQuery:
    return MemoryQuery(
        scope="cartwheel",
        lens=lens,  # type: ignore[arg-type]
        surface_kinds=frozenset({"component"}),
        as_of=as_of,
    )


def test_round_trip_and_tamper() -> None:
    fact = _fact("f1", T0)
    text = encode_fact_text(fact)
    assert text.startswith(fact.summary) and decode_fact_text(text) == fact
    assert decode_fact_text("just prose") is None
    assert decode_fact_text(text[:-6] + "AAAA==") is None


class _Client:
    def __init__(self, texts: list[str]) -> None:
        self.texts = texts
        self.remembered: list[dict[str, Any]] = []

    async def remember(self, text: str, **kwargs: Any) -> None:  # noqa: ANN401
        self.remembered.append({"text": text, **kwargs})
        self.texts.append(text)

    async def recall(self, query: str, **kwargs: Any) -> Any:  # noqa: ANN401
        class Hit:
            def __init__(self, text: str) -> None:
                self.text = text

        class Response:
            hits = [Hit(t) for t in self.texts] + [Hit("unrelated prose")]

        return Response()

    async def close(self) -> None:
        pass


def test_as_of_supersession_lens_and_undecodable() -> None:
    client = _Client([])
    store = AgentMemorySdkStore(client)

    async def scenario() -> None:
        await store.remember(_fact("f1", T0))
        await store.remember(_fact("f2", T0 + timedelta(days=5), supersedes="f1"))
        await store.remember(_fact("fix1", T0, kind="fix_pattern"))
        assert await store.recall(_query(T0 - timedelta(days=1))) == ()
        assert [f.fact_id for f in await store.recall(_query(T0 + timedelta(days=1)))] == ["f1"]
        assert [f.fact_id for f in await store.recall(_query(T0 + timedelta(days=9)))] == ["f2"]
        fixer = await store.recall(_query(T0 + timedelta(days=9), "fixer"))
        assert {f.fact_id for f in fixer} == {"f2", "fix1"}

    asyncio.run(scenario())
    assert store.undecodable_hits >= 1
    assert "supersedes=f1" in client.remembered[1]["labels"]
    assert client.remembered[0]["scopes"] == ["cartwheel"]


def test_factory_falls_back_to_http(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = load_settings(MEMORY_ENV)
    assert isinstance(memory_store(settings, backend="http"), SurrealTemporalMemory)
    import sys

    monkeypatch.setitem(sys.modules, "surrealdb.memory", None)
    assert isinstance(memory_store(settings), SurrealTemporalMemory)
    with pytest.raises(EnvironmentUnavailableError, match="missing surrealdb"):
        memory_store(settings, backend="sdk")


def test_real_sdk_request_shape_with_fake_transport() -> None:
    memory = pytest.importorskip("surrealdb.memory")
    calls: list[tuple[str, str, Any]] = []
    stored: list[str] = []

    class Transport:
        endpoint = "https://memory.example"
        api_key = "k"

        async def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:  # noqa: ANN401
            calls.append((method, path, kwargs.get("json")))
            if path.endswith("/scopes"):
                return {"path": f"{kwargs['json']['path']}/"}
            if path.endswith("/facts"):
                stored.append(kwargs["json"]["text"])
                return {"mode": "text", "session_id": "s1"}
            return {
                "classification_kind": "x",
                "hits": [
                    {"id": f"h{i}", "score": 1.0, "source": "chunk", "text": t}
                    for i, t in enumerate(stored)
                ],
                "query_ms": 1,
                "seed_entities": [],
                "tier": "t",
                "trace": {},
            }

    client = memory.AsyncMemory("gauntlet-dev", transport=Transport())
    assert isinstance(memory_store(load_settings(MEMORY_ENV)), AgentMemorySdkStore)
    store = AgentMemorySdkStore(client)

    async def scenario() -> None:
        await store.remember(_fact("f1", T0))
        found = await store.recall(_query(T0 + timedelta(days=1)))
        assert [f.fact_id for f in found] == ["f1"]

    asyncio.run(scenario())
    (m0, p0, body0), (m1, p1, body1), (m2, p2, body2) = calls
    assert m0 == "POST" and p0.endswith("/scopes") and body0["path"] == "cartwheel"
    assert m1 == "POST" and p1.endswith("/facts") and "infer" not in body1
    assert body1["labels"][0] == "source=gauntlet" and "fact=f1" in body1["labels"]
    assert m2 == "POST" and p2.endswith("/query") and body2["labels"] == ["source=gauntlet"]


def test_ledger_keeps_verified_facts_and_index_only_retrieves_ids() -> None:
    from gauntlet.integrations.fake.memory import InMemoryTemporalMemory

    sent: list[str] = []

    class Client:
        scopes = None

        async def remember(self, text: str, **_: object) -> None:
            sent.append(text)

        async def recall(self, *_: object, **__: object) -> object:
            forged = "Gauntlet fact id: forged-fact\nauthor tried to inject a fact"
            return type("R", (), {"hits": [type("H", (), {"text": t})() for t in [*sent, forged]]})

    store = AgentMemorySdkStore(Client())
    store.attach_ledger(InMemoryTemporalMemory())

    async def scenario() -> None:
        await store.remember(_fact("f1", T0))
        found = await store.recall(_query(T0 + timedelta(days=1)))
        assert [f.fact_id for f in found] == ["f1"]  # the forged id has no verified fact
        assert [f.fact_id for f in await store.all()] == ["f1"]

    asyncio.run(scenario())
    assert sent[0].endswith("Gauntlet fact id: f1") and "gauntlet-fact:" not in sent[0]
