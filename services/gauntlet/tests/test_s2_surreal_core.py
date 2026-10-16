"""SurrealDB core adapters: offline transport tests + a local-database test.

The local test runs only when SURREAL_TEST_URL and SURREAL_TEST_PASS point at a disposable
local SurrealDB (e.g. infra/local docker compose). It never targets a non-loopback host.
"""

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
import pytest

from gauntlet.contracts import HistoricalDecision, LineageEdge, NodeRef, RunEvent, ToolEvent
from gauntlet.persistence.surreal_client import SurrealHttpClient, SurrealQueryError, http_base_url
from gauntlet.persistence.surreal_store import (
    SurrealLineageStore,
    SurrealRunStore,
    apply_core_schema,
)
from gauntlet.ports.errors import (
    DuplicateIdempotencyKeyError,
    EnvironmentUnavailableError,
    EventSequenceConflictError,
)

NOW = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
HASH = "a" * 64


def _event(run_id: str, sequence: int, idem: str | None = None) -> RunEvent:
    return RunEvent(
        run_id=run_id,
        event_id=f"evt-{sequence}",
        sequence=sequence,
        created_at=NOW,
        actor="gauntlet",
        event_type="plan_frozen",
        idempotency_key=idem,
        payload={"plan_sha256": HASH},
    )


def _client(handler: httpx.MockTransport) -> SurrealHttpClient:
    return SurrealHttpClient(
        url="ws://127.0.0.1:8001",
        namespace="ns",
        database="db",
        user="root",
        password="pw-test",
        transport=handler,
    )


def _reply(*statements: tuple[str, object]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": 1,
            "result": [{"status": s, "result": r, "time": "1ms"} for s, r in statements],
        },
    )


def test_url_conversion() -> None:
    assert http_base_url("ws://127.0.0.1:8001") == "http://127.0.0.1:8001"
    assert http_base_url("wss://db.example/rpc") == "https://db.example"
    with pytest.raises(ValueError):
        http_base_url("ftp://x")


def test_query_binds_variables_and_sends_headers() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _reply(("OK", []))

    store = SurrealRunStore(_client(httpx.MockTransport(handle)))
    asyncio.run(store.list_events("run-1"))
    request = seen[0]
    assert request.url.path == "/rpc"
    assert request.headers["surreal-ns"] == "ns" and request.headers["surreal-db"] == "db"
    body = json.loads(request.content)
    assert body["method"] == "query"
    assert "run-1" not in body["params"][0]  # values are bound, never interpolated
    assert body["params"][1] == {"run_id": "run-1", "after": -1}


@pytest.mark.parametrize(
    ("detail", "error"),
    [
        ("An error occurred: sequence_conflict", EventSequenceConflictError),
        ("An error occurred: duplicate_idempotency_key", DuplicateIdempotencyKeyError),
        ("The query was not executed due to a failed transaction", EventSequenceConflictError),
    ],
)
def test_append_maps_errors(detail: str, error: type[Exception]) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return _reply(("ERR", detail))

    store = SurrealRunStore(_client(httpx.MockTransport(handle)))
    with pytest.raises(error):
        asyncio.run(store.append_event(_event("run-1", 0)))


def test_auth_and_transport_failures_are_environment_errors() -> None:
    store = SurrealRunStore(_client(httpx.MockTransport(lambda r: httpx.Response(401))))
    with pytest.raises(EnvironmentUnavailableError, match="credentials"):
        asyncio.run(store.list_events("run-1"))

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    store = SurrealRunStore(_client(httpx.MockTransport(boom)))
    with pytest.raises(EnvironmentUnavailableError) as raised:
        asyncio.run(store.list_events("run-1"))
    assert "pw-test" not in str(raised.value)


def test_corrupt_row_is_not_fabricated() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return _reply(("OK", [{"doc": {"run_id": "r"}, "sequence": 0}]))

    store = SurrealRunStore(_client(httpx.MockTransport(handle)))
    with pytest.raises(EnvironmentUnavailableError, match="no longer matches"):
        asyncio.run(store.list_events("r"))


def test_unexpected_statement_error_propagates() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return _reply(("ERR", "Parse error"))

    store = SurrealLineageStore(_client(httpx.MockTransport(handle)))
    with pytest.raises(SurrealQueryError):
        asyncio.run(store.get_decision("dec-1"))


# ---- local SurrealDB (real database, loopback only) ----

LOCAL_URL = os.environ.get("SURREAL_TEST_URL")
LOCAL_PASS = os.environ.get("SURREAL_TEST_PASS")
local = pytest.mark.skipif(
    not (LOCAL_URL and LOCAL_PASS), reason="set SURREAL_TEST_URL/SURREAL_TEST_PASS (local only)"
)


def _local_client() -> SurrealHttpClient:
    assert LOCAL_URL and LOCAL_PASS
    assert urlsplit(LOCAL_URL).hostname in {"127.0.0.1", "localhost"}, "local database only"
    return SurrealHttpClient(
        url=LOCAL_URL,
        namespace="gauntlet_test",
        database=f"t{uuid4().hex[:12]}",
        user=os.environ.get("SURREAL_TEST_USER", "root"),
        password=LOCAL_PASS,
    )


@local
def test_local_run_store_append_only() -> None:
    async def scenario() -> None:
        client = _local_client()
        await apply_core_schema(client)
        await apply_core_schema(client)  # idempotent
        store = SurrealRunStore(client)
        await store.append_event(_event("run-a", 0, "k0"))
        await store.append_event(_event("run-a", 1))
        with pytest.raises(EventSequenceConflictError):
            await store.append_event(_event("run-a", 1))
        with pytest.raises(EventSequenceConflictError):
            await store.append_event(_event("run-a", 5))
        with pytest.raises(DuplicateIdempotencyKeyError):
            await store.append_event(_event("run-a", 2, "k0"))
        concurrent = await asyncio.gather(
            store.append_event(_event("run-a", 2)),
            store.append_event(_event("run-a", 2)),
            return_exceptions=True,
        )
        assert sum(isinstance(item, EventSequenceConflictError) for item in concurrent) == 1
        events = await store.list_events("run-a")
        assert [e.sequence for e in events] == [0, 1, 2]
        assert events[0] == _event("run-a", 0, "k0")
        assert [e.sequence for e in await store.list_events("run-a", after_sequence=0)] == [1, 2]
        await client.close()

    asyncio.run(scenario())


@local
def test_local_lineage_and_history() -> None:
    async def scenario() -> None:
        client = _local_client()
        await apply_core_schema(client)
        store = SurrealLineageStore(client)
        chunk = NodeRef(kind="document_chunk", node_id="kb-refund-7")
        decision = NodeRef(kind="decision", node_id="dec-1")
        memory = NodeRef(kind="memory", node_id="mem-1")
        edges = [
            LineageEdge(
                edge_id="e1",
                source=chunk,
                relation="retrieved_by",
                target=decision,
                recorded_at=NOW,
            ),
            LineageEdge(
                edge_id="e2", source=decision, relation="wrote", target=memory, recorded_at=NOW
            ),
        ]
        for edge in edges:
            await store.record_edge(edge)
        with pytest.raises(EventSequenceConflictError):
            await store.record_edge(edges[0])
        assert await store.edges_from(chunk) == (edges[0],)
        assert await store.edges_to(decision) == (edges[0],)
        assert await store.edges_from(decision) == (edges[1],)
        assert await store.edges_to(chunk) == ()

        record = HistoricalDecision(
            decision_id="dec-1",
            target_id="cartwheel-fixture",
            occurred_at=NOW,
            agent_id="refund-agent",
            actor_ref="user-1",
            model_id="model-x",
            prompt_version="v1",
            policy_version="v1",
            structured_action="refund",
        )
        await store.record_decision(record)
        assert await store.get_decision("dec-1") == record
        assert await store.get_decision("missing") is None
        tool = [
            ToolEvent(
                event_id=f"te-{i}",
                decision_id="dec-1",
                target_id="cartwheel-fixture",
                tool_name="request_refund",
                actor_ref="user-1",
                arguments_hash=HASH,
                occurred_at=NOW + timedelta(minutes=i),
                outcome="succeeded",
            )
            for i in range(3)
        ]
        for item in reversed(tool):
            await store.record_tool_event(item)
        found = await store.tool_events(
            "cartwheel-fixture", "request_refund", NOW, NOW + timedelta(minutes=1)
        )
        assert found == tuple(tool[:2])
        await client.close()

    asyncio.run(scenario())
