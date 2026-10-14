"""Offline ports must preserve history and refuse invented replay results."""

import asyncio
from pathlib import Path

import pytest
from gauntlet.contracts import MissingInput, ReplayResult, ReplaySpec, RunEvent
from gauntlet.integrations.fake.replay import FakeReplayEngine
from gauntlet.integrations.fake.storage import FakeRunStore
from gauntlet.ports.errors import DuplicateIdempotencyKeyError, EventSequenceConflictError

GOLDENS = Path(__file__).resolve().parents[3] / "docs/contracts/examples"


def event() -> RunEvent:
    return RunEvent.model_validate_json((GOLDENS / "run-event.v1.json").read_text())


def replay() -> ReplaySpec:
    value = ReplaySpec.model_validate_json((GOLDENS / "replay-spec-control.v1.json").read_text())
    return value.model_copy(update={"image_digest": "sha256:" + "a" * 64})


@pytest.mark.asyncio
async def test_store_snapshots_payloads_and_returns_ordered_isolated_runs() -> None:
    store = FakeRunStore(initial_sequence=1)
    first = event()
    await store.append_event(first)
    first.payload["plan_hash"] = "mutated"
    second = first.model_copy(
        update={"sequence": 2, "event_id": "event-002", "idempotency_key": "run-001:executing"}
    )
    await store.append_event(second)
    records = await store.list_events("run-001")
    assert [item.sequence for item in records] == [1, 2]
    assert records[0].payload["plan_hash"] == "example-not-a-real-hash"
    records[0].payload.clear()
    assert (await store.list_events("run-001"))[0].payload
    assert [item.sequence for item in await store.list_events("run-001", 1)] == [2]
    assert await store.list_events("another-run") == ()


@pytest.mark.asyncio
async def test_store_rejects_sequence_gaps_duplicates_and_concurrent_overwrite() -> None:
    store = FakeRunStore(initial_sequence=1)
    first = event()
    with pytest.raises(EventSequenceConflictError):
        await store.append_event(first.model_copy(update={"sequence": 2}))
    results = await asyncio.gather(
        store.append_event(first), store.append_event(first), return_exceptions=True
    )
    assert sum(result is None for result in results) == 1
    assert isinstance(
        next(result for result in results if result is not None), DuplicateIdempotencyKeyError
    )
    with pytest.raises(EventSequenceConflictError):
        await store.append_event(
            first.model_copy(update={"sequence": 1, "idempotency_key": "new-key"})
        )
    assert len(await store.list_events("run-001")) == 1


@pytest.mark.asyncio
async def test_replay_only_returns_result_for_the_exact_recorded_world() -> None:
    spec = replay()
    result = ReplayResult(
        replay_id=spec.replay_id,
        status="matched",
        observed_action="deny_refund",
        evidence_ids=("recorded-001",),
    )
    engine = FakeReplayEngine(((spec, result),))
    assert await engine.replay(spec) == result
    changed = spec.model_copy(update={"policy_version": "different-policy"})
    assert (await engine.replay(changed)).status == "not_replayable"
    assert (await FakeReplayEngine(()).replay(spec)).status == "not_replayable"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field",
    [
        "image_digest",
        "tool_results_hash",
        "input_messages_hash",
        "model_id",
        "logical_timestamp",
        "memory_snapshot_hash",
    ],
)
async def test_replay_missing_pins_cannot_return_a_recorded_match(field: str) -> None:
    spec = replay().model_copy(update={field: None})
    engine = FakeReplayEngine(((spec, ReplayResult(replay_id=spec.replay_id, status="matched")),))
    result = await engine.replay(spec)
    assert result.status == "not_replayable"
    assert result.observed_action is None
    assert result.limitations


@pytest.mark.asyncio
async def test_critical_missing_input_overrides_preloaded_result() -> None:
    spec = replay().model_copy(
        update={
            "missing_inputs": (MissingInput(field="ledger", reason="not recorded", critical=True),)
        }
    )
    engine = FakeReplayEngine(((spec, ReplayResult(replay_id=spec.replay_id, status="matched")),))
    assert (await engine.replay(spec)).status == "not_replayable"
