"""Process-local, append-only, single-use approval store."""

from gauntlet.contracts import ApprovalRecord
from gauntlet.ports.errors import ApprovalAlreadyConsumedError, DuplicateApprovalError


class InMemoryApprovalStore:
    def __init__(self) -> None:
        self._records: dict[str, ApprovalRecord] = {}
        self._consumed: dict[str, str] = {}

    async def save(self, record: ApprovalRecord) -> None:
        if record.approval_id in self._records:
            raise DuplicateApprovalError("approval already exists")
        self._records[record.approval_id] = record.model_copy(deep=True)

    async def get(self, approval_id: str) -> ApprovalRecord | None:
        record = self._records.get(approval_id)
        return record.model_copy(deep=True) if record else None

    async def consume(self, approval_id: str, consumer_ref: str) -> None:
        if approval_id in self._consumed:
            raise ApprovalAlreadyConsumedError("approval was already used")
        self._consumed[approval_id] = consumer_ref
