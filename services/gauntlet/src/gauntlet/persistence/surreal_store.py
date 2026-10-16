"""SurrealDB core adapters for `RunStore`, `LineageStore` and `HistoricalEventStore`.

Each DTO is stored whole as `doc` (its JSON form) next to a few indexed columns, and read
back through Pydantic, so a row that no longer fits the contract fails loudly instead of
becoming a fabricated value. Writes are append-only: record IDs are deterministic and
`CREATE` refuses an existing record, so history is never overwritten.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Final

from pydantic import ValidationError

from gauntlet.contracts import HistoricalDecision, LineageEdge, NodeRef, RunEvent, ToolEvent
from gauntlet.ports.errors import (
    DuplicateIdempotencyKeyError,
    EnvironmentUnavailableError,
    EventSequenceConflictError,
)

from .surreal_client import JsonValue, SurrealHttpClient, SurrealQueryError, rows

SCHEMA_VERSION: Final = "s2-core-1"

# Versioned, idempotent schema. Unique indexes are the concurrency guard for appends.
CORE_SCHEMA: Final = """
DEFINE TABLE IF NOT EXISTS run_event SCHEMALESS;
DEFINE INDEX IF NOT EXISTS run_event_seq ON run_event FIELDS run_id, sequence UNIQUE;
DEFINE INDEX IF NOT EXISTS run_event_eid ON run_event FIELDS run_id, event_id UNIQUE;
DEFINE INDEX IF NOT EXISTS run_event_idem ON run_event FIELDS run_id, idempotency_key;
DEFINE TABLE IF NOT EXISTS lineage_node SCHEMALESS;
DEFINE TABLE IF NOT EXISTS influences TYPE RELATION SCHEMALESS;
DEFINE INDEX IF NOT EXISTS influences_edge ON influences FIELDS edge_id UNIQUE;
DEFINE TABLE IF NOT EXISTS decision SCHEMALESS;
DEFINE TABLE IF NOT EXISTS tool_event SCHEMALESS;
DEFINE INDEX IF NOT EXISTS tool_event_window ON tool_event FIELDS target_id, tool_name, occurred_at;
DEFINE TABLE IF NOT EXISTS schema_migration SCHEMALESS;
"""


async def apply_core_schema(client: SurrealHttpClient) -> None:
    await client.query(CORE_SCHEMA)
    await client.query(
        "UPSERT type::thing('schema_migration', $version) SET applied = true;",
        {"version": SCHEMA_VERSION},
    )


_APPEND_EVENT: Final = """
BEGIN TRANSACTION;
LET $last = (SELECT VALUE sequence FROM run_event WHERE run_id = $run_id
             ORDER BY sequence DESC LIMIT 1)[0];
IF $idem != NONE AND $idem != NULL AND array::len(
    (SELECT VALUE sequence FROM run_event WHERE run_id = $run_id AND idempotency_key = $idem)
) > 0 { THROW "duplicate_idempotency_key" };
IF $last = NONE { IF $sequence != $initial { THROW "sequence_conflict" } }
ELSE IF $sequence != $last + 1 { THROW "sequence_conflict" };
CREATE type::thing('run_event', [$run_id, $sequence]) CONTENT {
    run_id: $run_id, sequence: $sequence, event_id: $event_id,
    idempotency_key: $idem, doc: $doc
};
COMMIT TRANSACTION;
"""


class SurrealRunStore:
    """Append-only run log. Sequence must be next; idempotency keys are single-use per run."""

    def __init__(self, client: SurrealHttpClient, *, initial_sequence: int = 0) -> None:
        if initial_sequence < 0:
            raise ValueError("initial sequence must be non-negative")
        self._client = client
        self._initial = initial_sequence

    async def append_event(self, event: RunEvent) -> None:
        variables: dict[str, JsonValue] = {
            "run_id": event.run_id,
            "sequence": event.sequence,
            "event_id": event.event_id,
            "idem": event.idempotency_key,
            "initial": self._initial,
            "doc": event.model_dump(mode="json"),
        }
        try:
            await self._client.query(_APPEND_EVENT, variables)
        except SurrealQueryError as exc:
            if "duplicate_idempotency_key" in exc.detail:
                raise DuplicateIdempotencyKeyError(
                    "idempotency key already used for this run"
                ) from None
            if (
                "sequence_conflict" in exc.detail
                or "already exists" in exc.detail
                or "already contains" in exc.detail
                or "failed transaction" in exc.detail
            ):
                raise EventSequenceConflictError(
                    "event sequence or identity conflicts with history"
                ) from None
            raise

    async def list_events(self, run_id: str, after_sequence: int = -1) -> tuple[RunEvent, ...]:
        result = await self._client.query(
            "SELECT doc, sequence FROM run_event WHERE run_id = $run_id AND sequence > $after "
            "ORDER BY sequence ASC;",
            {"run_id": run_id, "after": after_sequence},
        )
        return tuple(_parse(RunEvent, row.get("doc")) for row in rows(result[0]))


def _node_key(node: NodeRef) -> list[JsonValue]:
    return [node.kind, node.node_id]


def _parse[T: (RunEvent, LineageEdge, HistoricalDecision, ToolEvent)](
    model: type[T], value: JsonValue
) -> T:
    try:
        return model.model_validate(value)
    except ValidationError:
        raise EnvironmentUnavailableError(
            f"stored {model.__name__} no longer matches its contract"
        ) from None


class SurrealLineageStore:
    """Graph of recorded influence: `lineage_node -> influences -> lineage_node`.

    Implements the read-only `LineageStore` and `HistoricalEventStore` ports, plus
    append-only `record_*` methods used by the trusted recorder (never by a model).
    """

    def __init__(self, client: SurrealHttpClient) -> None:
        self._client = client

    async def record_edge(self, edge: LineageEdge) -> None:
        try:
            await self._client.query(
                """
                BEGIN TRANSACTION;
                LET $src = type::thing('lineage_node', $source);
                LET $dst = type::thing('lineage_node', $target);
                UPSERT $src SET kind = $source[0], node_id = $source[1];
                UPSERT $dst SET kind = $target[0], node_id = $target[1];
                RELATE $src->influences->$dst CONTENT {
                    edge_id: $edge_id, relation: $relation, doc: $doc
                };
                COMMIT TRANSACTION;
                """,
                {
                    "source": _node_key(edge.source),
                    "target": _node_key(edge.target),
                    "edge_id": edge.edge_id,
                    "relation": edge.relation,
                    "doc": edge.model_dump(mode="json"),
                },
            )
        except SurrealQueryError as exc:
            if "influences_edge" in exc.detail or "already" in exc.detail:
                raise EventSequenceConflictError("lineage edge already recorded") from None
            raise

    async def edges_from(self, node: NodeRef) -> tuple[LineageEdge, ...]:
        return await self._edges("in", node)

    async def edges_to(self, node: NodeRef) -> tuple[LineageEdge, ...]:
        return await self._edges("out", node)

    async def _edges(self, side: str, node: NodeRef) -> tuple[LineageEdge, ...]:
        column = "in" if side == "in" else "out"  # fixed identifiers, never caller input
        statement = (
            f"SELECT doc, edge_id FROM influences WHERE {column} = "
            "type::thing('lineage_node', $node) ORDER BY edge_id ASC;"
        )
        result = await self._client.query(statement, {"node": _node_key(node)})
        return tuple(_parse(LineageEdge, row.get("doc")) for row in rows(result[0]))

    async def record_decision(self, decision: HistoricalDecision) -> None:
        await self._create(
            "decision",
            decision.decision_id,
            {"target_id": decision.target_id, "doc": decision.model_dump(mode="json")},
        )

    async def record_tool_event(self, event: ToolEvent) -> None:
        await self._create(
            "tool_event",
            event.event_id,
            {
                "target_id": event.target_id,
                "tool_name": event.tool_name,
                "occurred_at": event.occurred_at.isoformat(),
                "doc": event.model_dump(mode="json"),
            },
            datetime_fields=("occurred_at",),
        )

    async def _create(
        self,
        table: str,
        record_id: str,
        content: dict[str, JsonValue],
        datetime_fields: tuple[str, ...] = (),
    ) -> None:
        casts = "".join(f", {name}: <datetime>$content.{name}" for name in datetime_fields)
        try:
            await self._client.query(
                f"CREATE type::thing($table, $id) CONTENT {{ doc: $content.doc{casts}, "
                "target_id: $content.target_id, tool_name: $content.tool_name };",
                {"table": table, "id": record_id, "content": content},
            )
        except SurrealQueryError as exc:
            if "already exists" in exc.detail:
                raise EventSequenceConflictError(f"{table} {record_id} already recorded") from None
            raise

    async def get_decision(self, decision_id: str) -> HistoricalDecision | None:
        result = await self._client.query(
            "SELECT doc FROM type::thing('decision', $id);", {"id": decision_id}
        )
        found = rows(result[0])
        return _parse(HistoricalDecision, found[0].get("doc")) if found else None

    async def tool_events(
        self, target_id: str, tool_name: str, start_at: datetime, end_at: datetime
    ) -> tuple[ToolEvent, ...]:
        result = await self._client.query(
            "SELECT doc, occurred_at FROM tool_event WHERE target_id = $target_id "
            "AND tool_name = $tool_name AND occurred_at >= <datetime>$start "
            "AND occurred_at <= <datetime>$end ORDER BY occurred_at ASC;",
            {
                "target_id": target_id,
                "tool_name": tool_name,
                "start": start_at.isoformat(),
                "end": end_at.isoformat(),
            },
        )
        return tuple(_parse(ToolEvent, row.get("doc")) for row in rows(result[0]))


def surreal_stores(
    client: SurrealHttpClient, *, initial_sequence: int = 0
) -> tuple[SurrealRunStore, SurrealLineageStore]:
    return SurrealRunStore(client, initial_sequence=initial_sequence), SurrealLineageStore(client)


__all__: Sequence[str] = (
    "CORE_SCHEMA",
    "SurrealLineageStore",
    "SurrealRunStore",
    "apply_core_schema",
    "surreal_stores",
)
