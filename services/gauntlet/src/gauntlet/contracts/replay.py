"""Replay protocol for isolated Gate/base/head, historical control and fix testing."""

from typing import Literal

from pydantic import Field

from .common import StrictDTO


class ReplaySpec(StrictDTO):
    replay_id: str
    mode: Literal["gate_compare", "historical_control", "historical_counterfactual", "fix_regression", "event_audit"]
    target_id: str
    source_sha: str
    fixture_id: str
    fixture_checksum: str
    image_digest: str | None = None
    decision_id: str | None = None
    model_id: str | None = None
    prompt_version: str | None = None
    policy_version: str | None = None
    kb_snapshot_hash: str | None = None
    memory_snapshot_hash: str | None = None
    tool_results_hash: str | None = None
    excluded_source_id: str | None = None
    missing_inputs: tuple[str, ...] = ()
    max_runtime_seconds: int = Field(default=180, ge=1, le=1800)


class ReplayResult(StrictDTO):
    replay_id: str
    status: Literal["matched", "different", "inconclusive", "not_replayable", "environment_error"]
    observed_action: str | None = None
    amount_minor: int | None = None
    state_hash: str | None = None
    evidence_ids: tuple[str, ...] = ()
    trace_ids: tuple[str, ...] = ()
