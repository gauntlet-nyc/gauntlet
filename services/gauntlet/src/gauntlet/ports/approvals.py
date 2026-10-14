"""Append-only, single-use approval storage."""

from typing import Protocol

from gauntlet.contracts import ApprovalRecord


class ApprovalStore(Protocol):
    async def save(self, record: ApprovalRecord) -> None:
        """Raise DuplicateApprovalError if ``record.approval_id`` exists. Never overwrite."""
        ...

    async def get(self, approval_id: str) -> ApprovalRecord | None: ...

    async def consume(self, approval_id: str, consumer_ref: str) -> None:
        """Atomically mark spent. Raise ApprovalAlreadyConsumedError if already consumed."""
        ...
