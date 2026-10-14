"""Gate DTOs. Tools and oracles are references, never executable model-generated code."""

from typing import Literal

from pydantic import Field, model_validator

from .common import SourceRef, StrictDTO

WorkerKind = Literal["ui", "accessibility", "workflow", "api", "concurrency", "ai_agent"]
GateStatus = Literal[
    "confirmed_regression", "confirmed_pre_existing", "confirmed_policy_violation",
    "suspected", "not_reproducible", "environment_error", "passed", "not_tested",
]
Attribution = Literal["introduced", "pre_existing", "unknown"]


class ChangeRequest(StrictDTO):
    repository_id: str = Field(min_length=1)
    base_sha: str = Field(min_length=7)
    head_sha: str = Field(min_length=7)
    fixture_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    feature_intent: str | None = Field(default=None, max_length=2048)


class AffectedSurface(StrictDTO):
    kind: Literal["route", "component", "api", "agent_tool", "style", "workflow"]
    identifier: str = Field(min_length=1)
    source_refs: tuple[SourceRef, ...]
    confidence: float = Field(ge=0, le=1)


class ChangeImpactMap(StrictDTO):
    base_sha: str
    head_sha: str
    changed_files: tuple[str, ...]
    surfaces: tuple[AffectedSurface, ...]
    coverage_gaps: tuple[str, ...] = ()


class ActionStep(StrictDTO):
    action: Literal["navigate", "resize", "click", "scroll", "type", "press", "inspect", "capture", "test_api", "chat"]
    target: str | None = None
    width: int | None = Field(default=None, ge=240, le=3840)
    height: int | None = Field(default=None, ge=240, le=2160)
    value: str | None = Field(default=None, max_length=5000)


class AttackSpec(StrictDTO):
    attack_id: str = Field(min_length=1)
    hypothesis: str = Field(min_length=1, max_length=2500)
    why_this_change: str = Field(min_length=1, max_length=2500)
    source_refs: tuple[SourceRef, ...]
    worker_kind: WorkerKind
    target_id: str = Field(min_length=1)
    fixture_id: str = Field(min_length=1)
    steps: tuple[ActionStep, ...] = Field(min_length=1, max_length=100)
    oracle_ids: tuple[str, ...] = Field(min_length=1, max_length=12)
    max_actions: int = Field(ge=1, le=100)
    max_runtime_seconds: int = Field(ge=1, le=900)

    @model_validator(mode="after")
    def actions_fit_budget(self) -> "AttackSpec":
        if len(self.steps) > self.max_actions:
            raise ValueError("steps cannot exceed max_actions")
        return self


class Observation(StrictDTO):
    attack_id: str
    environment_id: str
    state_checksum: str
    action_count: int = Field(ge=0)
    evidence_ids: tuple[str, ...] = ()
    trace_ids: tuple[str, ...] = ()
    details: dict[str, str] = Field(default_factory=dict)


class Finding(StrictDTO):
    finding_id: str
    attack_id: str
    status: GateStatus
    attribution: Attribution
    oracle_ids: tuple[str, ...]
    head_reproductions: int = Field(ge=0)
    head_attempts: int = Field(ge=0)
    base_reproductions: int = Field(ge=0)
    base_attempts: int = Field(ge=0)
    evidence_ids: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
