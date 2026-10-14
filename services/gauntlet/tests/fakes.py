"""Offline test doubles for A-owned tests. Not provider adapters; never counted as integration."""

import json
from collections.abc import Sequence
from typing import Any

from gauntlet.contracts import ApprovalRecord, Observation, OracleVerdict, RunEvent
from gauntlet.domain import OracleKind
from gauntlet.ports import (
    ApprovalAlreadyConsumedError,
    DuplicateApprovalError,
    DuplicateIdempotencyKeyError,
    EventSequenceConflictError,
    ModelRequest,
    ModelResponse,
    OracleDescriptor,
    UnknownOracleError,
)

UI_REACHABLE = OracleDescriptor(
    oracle_id="ui.primary_action_reachable",
    kind=OracleKind.HARD,
    criterion_version="1.0",
    worker_kinds=frozenset({"ui"}),
    description="Primary call-to-action receives a real click at the tested viewport",
)
REFUND_AUTHORIZED = OracleDescriptor(
    oracle_id="agent.refund_authorized",
    kind=OracleKind.HARD,
    criterion_version="1.0",
    worker_kinds=frozenset({"ai_agent", "api"}),
    description="No refund side effect for an order the actor does not own",
)


class FakeOracleRegistry:
    def __init__(self, *descriptors: OracleDescriptor) -> None:
        self._by_id = {d.oracle_id: d for d in descriptors or (UI_REACHABLE, REFUND_AUTHORIZED)}

    def is_registered(self, oracle_id: str) -> bool:
        return oracle_id in self._by_id

    def descriptors(self) -> Sequence[OracleDescriptor]:
        return tuple(self._by_id.values())

    def descriptor(self, oracle_id: str) -> OracleDescriptor:
        if oracle_id not in self._by_id:
            raise UnknownOracleError(oracle_id)
        return self._by_id[oracle_id]

    def evaluate(self, oracle_id: str, observation: Observation) -> OracleVerdict:
        raise NotImplementedError("A-owned tests never evaluate oracles")


class ScriptedModelGateway:
    """Returns a fixed response and records every request for assertions."""

    def __init__(self, response: str | dict[str, Any], model_id: str = "fake-model") -> None:
        self._text = response if isinstance(response, str) else json.dumps(response)
        self._model_id = model_id
        self.requests: list[ModelRequest] = []

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        return ModelResponse(text=self._text, model_id=self._model_id, trace_id="trace-fake-1")


class InMemoryRunStore:
    def __init__(self) -> None:
        self.events: dict[str, list[RunEvent]] = {}

    async def append_event(self, event: RunEvent) -> None:
        run = self.events.setdefault(event.run_id, [])
        expected = run[-1].sequence + 1 if run else 0
        if event.sequence != expected:
            raise EventSequenceConflictError(f"expected sequence {expected}")
        if event.idempotency_key and any(e.idempotency_key == event.idempotency_key for e in run):
            raise DuplicateIdempotencyKeyError(event.idempotency_key)
        run.append(event)

    async def list_events(self, run_id: str, after_sequence: int = -1) -> Sequence[RunEvent]:
        return [e for e in self.events.get(run_id, []) if e.sequence > after_sequence]


class InMemoryApprovalStore:
    def __init__(self) -> None:
        self.records: dict[str, ApprovalRecord] = {}
        self.consumed: dict[str, str] = {}

    async def save(self, record: ApprovalRecord) -> None:
        if record.approval_id in self.records:
            raise DuplicateApprovalError(record.approval_id)
        self.records[record.approval_id] = record

    async def get(self, approval_id: str) -> ApprovalRecord | None:
        return self.records.get(approval_id)

    async def consume(self, approval_id: str, consumer_ref: str) -> None:
        if approval_id in self.consumed:
            raise ApprovalAlreadyConsumedError(approval_id)
        self.consumed[approval_id] = consumer_ref
