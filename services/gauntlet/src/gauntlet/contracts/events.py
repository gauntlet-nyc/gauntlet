"""Versioned append-only event envelope for REST and SSE."""

from pydantic import Field

from .common import Identifier, StrictDTO, UtcDatetime

PayloadValue = str | int | float | bool | None


class RunEvent(StrictDTO):
    run_id: Identifier
    event_id: Identifier
    sequence: int = Field(ge=0)
    created_at: UtcDatetime
    actor: Identifier
    event_type: str = Field(max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    idempotency_key: Identifier | None = None
    snapshot_id: Identifier | None = None
    payload: dict[Identifier, PayloadValue] = Field(default_factory=dict, max_length=64)
    trace_id: Identifier | None = None
