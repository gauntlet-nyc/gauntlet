"""Process-local stores for the demo API. Not durable; a restart clears runs and approvals."""

from gauntlet.contracts import ApprovalRecord


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
