"""Process-local stores for the demo API. Not durable; a restart clears runs and approvals."""

from gauntlet.contracts import ApprovalRecord, TemporalMemoryFact
from gauntlet.memory.surreal_memory import LENS_KINDS
from gauntlet.ports.memory import MemoryQuery


class InMemoryApprovalStore:
    """ApprovalStore port. Each approval is spendable once."""

    def __init__(self) -> None:
        self._records: dict[str, ApprovalRecord] = {}
        self._consumed: dict[str, str] = {}

    async def save(self, record: ApprovalRecord) -> None:
        if record.approval_id in self._records:
            raise ValueError("approval IDs are immutable")
        self._records[record.approval_id] = record

    async def get(self, approval_id: str) -> ApprovalRecord | None:
        return self._records.get(approval_id)

    async def consume(self, approval_id: str, consumer_ref: str) -> None:
        if approval_id in self._consumed:
            raise ValueError("approval already used")
        self._consumed[approval_id] = consumer_ref

    def list(self) -> list[ApprovalRecord]:
        return sorted(self._records.values(), key=lambda r: r.decided_at)

    def consumed_by(self, approval_id: str) -> str | None:
        return self._consumed.get(approval_id)


class InProcessTemporalMemory:
    """OFFLINE MemoryReader/MemoryWriter with Agent Memory semantics, held in API memory.

    Append-only; `recall` returns facts in scope that the lens may see and that were known at
    `as_of`. The planner re-filters with `select_memory`. Live: SurrealTemporalMemory.
    """

    def __init__(self) -> None:
        self._facts: list[TemporalMemoryFact] = []

    async def remember(self, fact: TemporalMemoryFact) -> None:
        if any(f.fact_id == fact.fact_id for f in self._facts):
            raise ValueError("memory facts are append-only")
        if fact.supersedes and not any(f.fact_id == fact.supersedes for f in self._facts):
            raise ValueError("superseded fact is unknown")
        self._facts.append(fact)

    async def recall(self, query: MemoryQuery) -> tuple[TemporalMemoryFact, ...]:
        kinds = LENS_KINDS[query.lens]
        return tuple(
            f
            for f in self._facts
            if f.scope == query.scope
            and f.kind in kinds
            and f.known_at <= query.as_of
            and query.surface_kinds.intersection(f.surface_kinds)
        )[: query.limit]

    def all(self) -> tuple[TemporalMemoryFact, ...]:
        return tuple(self._facts)
