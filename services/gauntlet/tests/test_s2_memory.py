"""Temporal memory adapter: offline request shape + local SurrealDB semantics."""

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
import pytest

from gauntlet.contracts import MemoryProvenance, TemporalMemoryFact
from gauntlet.memory.surreal_memory import MemoryRejectedError, SurrealTemporalMemory
from gauntlet.persistence.factory import core_client, memory_client
from gauntlet.persistence.surreal_client import SurrealHttpClient
from gauntlet.ports.memory import MemoryQuery
from gauntlet.settings import MissingSettingError, load_settings

T0 = datetime(2026, 10, 1, tzinfo=UTC)


def _fact(
    fact_id: str,
    known: datetime,
    *,
    supersedes: str | None = None,
    kind: str = "ui_occlusion",
    scope: str = "cartwheel",
) -> TemporalMemoryFact:
    return TemporalMemoryFact(
        fact_id=fact_id,
        kind=kind,  # type: ignore[arg-type]
        summary="Floating help overlaps checkout on narrow viewports",
        verification="confirmed",
        trust="verified_test",
        scope=scope,
        surface_kinds=("component", "style"),
        source=MemoryProvenance(finding_id="finding-1", oracle_id="ui.primary_action_reachable"),
        known_at=known,
        valid_from=known,
        supersedes=supersedes,
    )


def test_factories_need_settings_and_use_separate_credentials() -> None:
    with pytest.raises(MissingSettingError, match="SURREAL_MEMORY_ENDPOINT"):
        memory_client(load_settings({}))
    with pytest.raises(MissingSettingError, match="SURREAL_PASS"):
        core_client(load_settings({}))
    settings = load_settings(
        {"SURREAL_MEMORY_ENDPOINT": "https://memory.example", "SURREAL_MEMORY_API_KEY": "k" * 20}
    )
    assert memory_client(settings) is not None


def test_recall_binds_query_and_filters_validity_offline() -> None:
    seen: list[dict[str, object]] = []
    expired = _fact("f-old", T0).model_copy(update={"valid_until": T0 + timedelta(days=1)})

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        docs = [
            {"doc": _fact("f-new", T0).model_dump(mode="json")},
            {"doc": expired.model_dump(mode="json")},
        ]
        return httpx.Response(
            200,
            json={"result": [{"status": "OK", "result": None}, {"status": "OK", "result": docs}]},
        )

    client = SurrealHttpClient(
        url="https://memory.example",
        namespace="agent_memory",
        database="ctx",
        token="t" * 20,
        transport=httpx.MockTransport(handle),
    )
    memory = SurrealTemporalMemory(client)
    facts = asyncio.run(
        memory.recall(
            MemoryQuery(
                scope="cartwheel",
                lens="planner",
                surface_kinds=frozenset({"style"}),
                as_of=T0 + timedelta(days=2),
            )
        )
    )
    assert [f.fact_id for f in facts] == ["f-new"]
    variables = seen[0]["params"][1]  # type: ignore[index]
    assert variables["scope"] == "cartwheel" and "fix_pattern" not in variables["kinds"]


LOCAL_URL = os.environ.get("SURREAL_TEST_URL")
LOCAL_PASS = os.environ.get("SURREAL_TEST_PASS")


@pytest.mark.skipif(not (LOCAL_URL and LOCAL_PASS), reason="local SurrealDB not configured")
def test_local_supersession_and_as_of() -> None:
    assert LOCAL_URL and LOCAL_PASS
    assert urlsplit(LOCAL_URL).hostname in {"127.0.0.1", "localhost"}

    async def scenario() -> None:
        client = SurrealHttpClient(
            url=LOCAL_URL,
            namespace="agent_memory_test",
            database=f"m{uuid4().hex[:12]}",
            user="root",
            password=LOCAL_PASS,
        )
        memory = SurrealTemporalMemory(client)
        await memory.ensure_schema()
        await memory.remember(_fact("f1", T0))
        await memory.remember(_fact("f2", T0 + timedelta(days=5), supersedes="f1"))
        await memory.remember(_fact("fix1", T0, kind="fix_pattern"))
        with pytest.raises(MemoryRejectedError, match="append-only"):
            await memory.remember(_fact("f1", T0))
        with pytest.raises(MemoryRejectedError, match="supersedes_unknown_fact"):
            await memory.remember(_fact("f3", T0, supersedes="nope"))
        await memory.remember(_fact("other", T0, scope="otherapp"))
        with pytest.raises(MemoryRejectedError, match="supersedes_other_scope"):
            await memory.remember(_fact("f4", T0 + timedelta(days=6), supersedes="other"))

        def query(as_of: datetime, lens: str = "planner") -> MemoryQuery:
            return MemoryQuery(
                scope="cartwheel",
                lens=lens,  # type: ignore[arg-type]
                surface_kinds=frozenset({"component"}),
                as_of=as_of,
            )

        before = await memory.recall(query(T0 - timedelta(days=1)))
        assert before == ()  # nothing known yet: no hindsight
        early = await memory.recall(query(T0 + timedelta(days=1)))
        assert [f.fact_id for f in early] == ["f1"]  # superseded later, visible then
        late = await memory.recall(query(T0 + timedelta(days=10)))
        assert [f.fact_id for f in late] == ["f2"]
        fixer = await memory.recall(query(T0 + timedelta(days=10), "fixer"))
        assert {f.fact_id for f in fixer} == {"f2", "fix1"}
        history = await memory.history("f2")
        assert [f.fact_id for f in history] == ["f2", "f1"]
        assert history[1].source.finding_id == "finding-1"
        await client.close()

    asyncio.run(scenario())
