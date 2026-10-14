"""Replay protocol for isolated Gate base/head, historical control and fix testing."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from gauntlet.domain import ReplayStatus

from .common import (
    GitSha,
    Identifier,
    MissingInput,
    Sha256Hex,
    ShortText,
    StrictDTO,
    UtcDatetime,
    VersionTag,
)

ReplayMode = Literal[
    "gate_compare",
    "historical_control",
    "historical_counterfactual",
    "fix_regression",
    "event_audit",
]
ImageDigest = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]

_HISTORICAL_MODES = frozenset({"historical_control", "historical_counterfactual", "event_audit"})


class ReplaySpec(StrictDTO):
    replay_id: Identifier
    mode: ReplayMode
    target_id: Identifier
    source_sha: GitSha
    image_digest: ImageDigest | None = None
    fixture_id: Identifier
    fixture_checksum: Sha256Hex
    decision_id: Identifier | None = None
    model_id: Identifier | None = None
    prompt_version: VersionTag | None = None
    policy_version: VersionTag | None = None
    tool_schema_hash: Sha256Hex | None = None
    kb_snapshot_hash: Sha256Hex | None = None
    memory_snapshot_hash: Sha256Hex | None = None
    tool_results_hash: Sha256Hex | None = None
    input_messages_hash: Sha256Hex | None = None
    seed: int | None = None
    logical_timestamp: UtcDatetime | None = None
    excluded_source_id: Identifier | None = None
    replacement_source_id: Identifier | None = None
    mutation_description: ShortText | None = None
    missing_inputs: tuple[MissingInput, ...] = ()
    max_runtime_seconds: int = Field(default=180, ge=1, le=1800)

    @model_validator(mode="after")
    def mode_requirements(self) -> Self:
        mutated = self.excluded_source_id is not None or self.replacement_source_id is not None
        if self.mode in _HISTORICAL_MODES and self.decision_id is None:
            raise ValueError(f"{self.mode} replay requires decision_id")
        if self.mode not in _HISTORICAL_MODES and self.decision_id is not None:
            raise ValueError(f"{self.mode} replay must not reference a historical decision")
        if self.mode == "historical_counterfactual" and not (mutated and self.mutation_description):
            raise ValueError("counterfactual replay must name the mutated source and describe it")
        if self.mode != "historical_counterfactual" and mutated:
            raise ValueError("only counterfactual replays may exclude or replace a source")
        return self


class ReplayResult(StrictDTO):
    replay_id: Identifier
    status: ReplayStatus
    observed_action: Identifier | None = None
    amount_minor: int | None = Field(default=None, ge=0)
    state_hash_before: Sha256Hex | None = None
    state_hash_after: Sha256Hex | None = None
    evidence_ids: tuple[Identifier, ...] = ()
    trace_ids: tuple[Identifier, ...] = ()
    limitations: tuple[ShortText, ...] = ()
