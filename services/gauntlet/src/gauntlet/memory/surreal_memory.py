"""`MemoryReader`/`MemoryWriter` on a SEPARATE SurrealDB memory context.

This is not the SurrealDB core run store: it uses its own endpoint, context (database) and
credentials (`SURREAL_MEMORY_*`). It speaks SurrealQL over HTTP RPC with bound variables.
The Agent Memory SDK (`surrealdb[memory]`, prerelease) is not an approved dependency yet;
when it is, a second backend can implement the same two ports.

Semantics:
- `remember` is append-only. A correction is a new fact whose `supersedes` names an existing
  fact in the same scope; the old fact is kept and stays inspectable via `history`.
- `recall` returns facts in scope, matching the lens and surfaces, known at `as_of` and valid
  at `as_of`, hiding facts superseded by something already known at `as_of`. So a fact that
  was superseded later is still returned for an earlier `as_of` (no hindsight).
- Provenance is part of the fact; confirmed facts must cite finding + oracle (the contract
  enforces this, and this adapter re-validates every stored row on read).
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Final

from pydantic import ValidationError

from gauntlet.contracts import MemoryKind, MemoryLens, TemporalMemoryFact
from gauntlet.persistence.surreal_client import (
    JsonValue,
    SurrealHttpClient,
    SurrealQueryError,
    rows,
)
from gauntlet.ports.errors import EnvironmentUnavailableError, PortError
from gauntlet.ports.memory import MemoryQuery

MEMORY_NAMESPACE: Final = "agent_memory"

# What each lens may see. Planner never sees fix patterns; fixer and investigator see all.
LENS_KINDS: Final[dict[MemoryLens, frozenset[MemoryKind]]] = {
    "planner": frozenset({"ui_occlusion", "authz_bypass", "workflow_state", "policy_conflict"}),
    "investigator": frozenset(
        {"ui_occlusion", "authz_bypass", "workflow_state", "policy_conflict", "fix_pattern"}
    ),
    "fixer": frozenset(
        {"ui_occlusion", "authz_bypass", "workflow_state", "policy_conflict", "fix_pattern"}
    ),
}

MEMORY_SCHEMA: Final = """
DEFINE TABLE IF NOT EXISTS memory_fact SCHEMALESS;
DEFINE INDEX IF NOT EXISTS memory_fact_scope ON memory_fact FIELDS scope, known_at;
DEFINE INDEX IF NOT EXISTS memory_fact_supersedes ON memory_fact FIELDS supersedes;
"""


class MemoryRejectedError(PortError):
    """The write would break append-only or supersession rules."""


def _ts(value: datetime) -> str:
    return value.isoformat()


class SurrealTemporalMemory:
    def __init__(self, client: SurrealHttpClient) -> None:
        self._client = client

    async def ensure_schema(self) -> None:
        await self._client.query(MEMORY_SCHEMA)

    async def remember(self, fact: TemporalMemoryFact) -> None:
        try:
            await self._client.query(
                """
                BEGIN TRANSACTION;
                IF $supersedes != NONE AND $supersedes != NULL {
                    LET $old = (SELECT scope, known_at
                        FROM type::thing('memory_fact', $supersedes))[0];
                    IF $old = NONE { THROW "supersedes_unknown_fact" };
                    IF $old.scope != $scope { THROW "supersedes_other_scope" };
                    IF $old.known_at > <datetime>$known_at { THROW "supersedes_newer_fact" };
                };
                CREATE type::thing('memory_fact', $fact_id) CONTENT {
                    scope: $scope, kind: $kind, surface_kinds: $surface_kinds,
                    known_at: <datetime>$known_at, supersedes: $supersedes, doc: $doc
                };
                COMMIT TRANSACTION;
                """,
                {
                    "fact_id": fact.fact_id,
                    "scope": fact.scope,
                    "kind": fact.kind,
                    "surface_kinds": list(fact.surface_kinds),
                    "known_at": _ts(fact.known_at),
                    "supersedes": fact.supersedes,
                    "doc": fact.model_dump(mode="json"),
                },
            )
        except SurrealQueryError as exc:
            for reason in (
                "supersedes_unknown_fact",
                "supersedes_other_scope",
                "supersedes_newer_fact",
            ):
                if reason in exc.detail:
                    raise MemoryRejectedError(reason) from None
            if "already exists" in exc.detail:
                raise MemoryRejectedError("fact_id already stored; memory is append-only") from None
            raise

    async def recall(self, query: MemoryQuery) -> tuple[TemporalMemoryFact, ...]:
        kinds = sorted(LENS_KINDS[query.lens])
        result = await self._client.query(
            """
            LET $known = (SELECT VALUE supersedes FROM memory_fact
                WHERE scope = $scope AND known_at <= <datetime>$as_of AND supersedes != NONE
                AND supersedes != NULL);
            SELECT doc, known_at FROM memory_fact
                WHERE scope = $scope AND kind IN $kinds
                AND known_at <= <datetime>$as_of
                AND surface_kinds ANYINSIDE $surfaces
                AND meta::id(id) NOTINSIDE $known
                ORDER BY known_at DESC;
            """,
            {
                "scope": query.scope,
                "kinds": [str(kind) for kind in kinds],
                "as_of": _ts(query.as_of),
                "surfaces": [str(kind) for kind in sorted(query.surface_kinds)],
            },
        )
        facts = [_parse(row.get("doc")) for row in rows(result[-1])]
        valid = [
            fact
            for fact in facts
            if fact.valid_from <= query.as_of
            and (fact.valid_until is None or query.as_of < fact.valid_until)
        ]
        valid.sort(key=lambda fact: (fact.known_at, fact.fact_id), reverse=True)
        return tuple(valid[: query.limit])

    async def history(self, fact_id: str) -> tuple[TemporalMemoryFact, ...]:
        """The fact and every fact it (transitively) supersedes, newest first. For audit."""
        chain: list[TemporalMemoryFact] = []
        current: str | None = fact_id
        seen: set[str] = set()
        while current is not None and current not in seen and len(chain) < 64:
            seen.add(current)
            result = await self._client.query(
                "SELECT doc FROM type::thing('memory_fact', $id);", {"id": current}
            )
            found = rows(result[0])
            if not found:
                break
            fact = _parse(found[0].get("doc"))
            chain.append(fact)
            current = fact.supersedes
        return tuple(chain)


def _parse(value: JsonValue) -> TemporalMemoryFact:
    try:
        return TemporalMemoryFact.model_validate(value)
    except ValidationError:
        raise EnvironmentUnavailableError(
            "stored memory fact no longer matches its contract"
        ) from None


__all__: Sequence[str] = ("LENS_KINDS", "MemoryRejectedError", "SurrealTemporalMemory")
