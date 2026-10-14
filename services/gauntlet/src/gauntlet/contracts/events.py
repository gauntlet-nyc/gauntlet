"""Versioned append-only event envelope for REST and SSE."""

from datetime import datetime

from pydantic import Field

from .common import StrictDTO


class RunEvent(StrictDTO):
    run_id: str
    event_id: str
    sequence: int = Field(ge=0)
    created_at: datetime
    actor: str
    event_type: str
    payload: dict[str, str] = Field(default_factory=dict)
    trace_id: str | None = None
