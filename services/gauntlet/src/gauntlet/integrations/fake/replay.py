"""Recorded offline replay. This adapter cannot invoke tools or external effects."""

from gauntlet.contracts import ReplayResult, ReplaySpec
from gauntlet.domain import ReplayStatus

_HISTORICAL_PINS = (
    "image_digest",
    "model_id",
    "prompt_version",
    "policy_version",
    "tool_schema_hash",
    "kb_snapshot_hash",
    "memory_snapshot_hash",
    "tool_results_hash",
    "input_messages_hash",
    "seed",
    "logical_timestamp",
)


class FakeReplayEngine:
    def __init__(self, recordings: tuple[tuple[ReplaySpec, ReplayResult], ...]) -> None:
        self._recordings: dict[str, ReplayResult] = {}
        for spec, result in recordings:
            if result.replay_id != spec.replay_id:
                raise ValueError("recording and replay IDs must match")
            key = spec.model_dump_json()
            if key in self._recordings:
                raise ValueError("duplicate replay recording")
            self._recordings[key] = result.model_copy(deep=True)

    async def replay(self, spec: ReplaySpec) -> ReplayResult:
        missing = [item.field for item in spec.missing_inputs if item.critical]
        if spec.mode in {"historical_control", "historical_counterfactual"}:
            missing.extend(field for field in _HISTORICAL_PINS if getattr(spec, field) is None)
        if missing:
            return ReplayResult(
                replay_id=spec.replay_id,
                status=ReplayStatus.NOT_REPLAYABLE,
                limitations=("Critical replay inputs are unavailable: " + ", ".join(missing),),
            )
        result = self._recordings.get(spec.model_dump_json())
        if result is None:
            return ReplayResult(
                replay_id=spec.replay_id,
                status=ReplayStatus.NOT_REPLAYABLE,
                limitations=("No offline recording exists for this exact replay specification.",),
            )
        return result.model_copy(deep=True)
