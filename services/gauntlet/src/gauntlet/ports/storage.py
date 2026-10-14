"""Append-only run event log (SurrealDB core in production)."""

from collections.abc import Sequence
from typing import Protocol

from gauntlet.contracts import RunEvent


class RunStore(Protocol):
    async def append_event(self, event: RunEvent) -> None:
        """Atomically append. Raise EventSequenceConflictError unless ``event.sequence`` is next,
        and DuplicateIdempotencyKeyError if its idempotency key was already used for the run."""
        ...

    async def list_events(self, run_id: str, after_sequence: int = -1) -> Sequence[RunEvent]:
        """Return events with sequence > ``after_sequence`` in ascending order."""
        ...
