"""Process-local append-only event store for credential-free integration checks."""

from gauntlet.contracts import RunEvent
from gauntlet.ports.errors import DuplicateIdempotencyKeyError, EventSequenceConflictError


class FakeRunStore:
    def __init__(self, *, initial_sequence: int) -> None:
        if initial_sequence < 0:
            raise ValueError("initial sequence must be non-negative")
        self._initial_sequence = initial_sequence
        self._events: dict[str, list[RunEvent]] = {}

    async def append_event(self, event: RunEvent) -> None:
        # No await between validation and append: atomic within this event loop.
        records = self._events.get(event.run_id, [])
        if event.idempotency_key is not None and any(
            item.idempotency_key == event.idempotency_key for item in records
        ):
            raise DuplicateIdempotencyKeyError("idempotency key already used for this run")
        expected = records[-1].sequence + 1 if records else self._initial_sequence
        if event.sequence != expected or any(item.event_id == event.event_id for item in records):
            raise EventSequenceConflictError("event sequence or identity conflicts with history")
        self._events.setdefault(event.run_id, []).append(event.model_copy(deep=True))

    async def list_events(self, run_id: str, after_sequence: int = -1) -> tuple[RunEvent, ...]:
        return tuple(
            event.model_copy(deep=True)
            for event in self._events.get(run_id, ())
            if event.sequence > after_sequence
        )
