"""Gate DTOs. Tools and oracles are references, never executable model-generated code."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from gauntlet.domain import (
    CONFIRMED_GATE_STATUSES,
    MIN_CONFIRMING_REPRODUCTIONS,
    Attribution,
    GateStatus,
    OracleKind,
    OracleOutcome,
    Severity,
)

from .common import (
    MAX_ITEMS,
    MAX_TEXT,
    GitSha,
    Identifier,
    OracleId,
    RelativePath,
    RoutePath,
    Sha256Hex,
    ShortText,
    SourceRef,
    StrictDTO,
    VersionTag,
)

WorkerKind = Literal["ui", "accessibility", "workflow", "api", "concurrency", "ai_agent"]
ActionKind = Literal[
    "navigate",
    "resize",
    "click",
    "scroll",
    "type",
    "press",
    "inspect",
    "capture",
    "test_api",
    "chat",
]
Selector = Annotated[str, Field(min_length=1, max_length=512)]


class ChangeRequest(StrictDTO):
    repository_id: Identifier
    base_sha: GitSha
    head_sha: GitSha
    fixture_id: Identifier
    target_id: Identifier
    max_cost_usd_cents: int = Field(ge=1, le=100_000)
    feature_intent: str | None = Field(default=None, max_length=2048)


class AffectedSurface(StrictDTO):
    kind: Literal["route", "component", "api", "agent_tool", "style", "workflow"]
    identifier: str = Field(min_length=1, max_length=512)
    source_refs: tuple[SourceRef, ...] = Field(min_length=1, max_length=MAX_ITEMS)
    confidence: float = Field(ge=0, le=1)


class ChangeImpactMap(StrictDTO):
    base_sha: GitSha
    head_sha: GitSha
    changed_files: tuple[RelativePath, ...] = Field(max_length=1000)
    surfaces: tuple[AffectedSurface, ...] = Field(max_length=MAX_ITEMS)
    coverage_gaps: tuple[ShortText, ...] = ()


# --- Typed action steps: a discriminated union, never free-form commands -------------------


class NavigateStep(StrictDTO):
    action: Literal["navigate"] = "navigate"
    path: RoutePath


class ResizeStep(StrictDTO):
    action: Literal["resize"] = "resize"
    width: int = Field(ge=240, le=3840)
    height: int = Field(ge=240, le=2160)


class ClickStep(StrictDTO):
    action: Literal["click"] = "click"
    target: Selector


class ScrollStep(StrictDTO):
    action: Literal["scroll"] = "scroll"
    target: Selector | None = None
    delta_y: int = Field(ge=-20_000, le=20_000)


class TypeStep(StrictDTO):
    action: Literal["type"] = "type"
    target: Selector
    value: str = Field(max_length=MAX_TEXT)


class PressStep(StrictDTO):
    action: Literal["press"] = "press"
    key: str = Field(pattern=r"^[A-Za-z0-9+]{1,32}$")


class InspectStep(StrictDTO):
    action: Literal["inspect"] = "inspect"
    target: Selector


class CaptureStep(StrictDTO):
    action: Literal["capture"] = "capture"
    label: Identifier | None = None


class ApiRequestStep(StrictDTO):
    action: Literal["test_api"] = "test_api"
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: RoutePath
    actor_id: Identifier
    body_json: str | None = Field(default=None, max_length=MAX_TEXT)


class ChatStep(StrictDTO):
    action: Literal["chat"] = "chat"
    agent_id: Identifier
    actor_id: Identifier
    message: str = Field(min_length=1, max_length=MAX_TEXT)


ActionStep = Annotated[
    NavigateStep
    | ResizeStep
    | ClickStep
    | ScrollStep
    | TypeStep
    | PressStep
    | InspectStep
    | CaptureStep
    | ApiRequestStep
    | ChatStep,
    Field(discriminator="action"),
]


class AttackSpec(StrictDTO):
    attack_id: Identifier
    hypothesis: ShortText
    why_this_change: ShortText
    expected_observation: ShortText
    source_refs: tuple[SourceRef, ...] = Field(min_length=1, max_length=MAX_ITEMS)
    worker_kind: WorkerKind
    target_id: Identifier
    fixture_id: Identifier
    steps: tuple[ActionStep, ...] = Field(min_length=1, max_length=MAX_ITEMS)
    oracle_ids: tuple[OracleId, ...] = Field(min_length=1, max_length=12)
    max_actions: int = Field(ge=1, le=MAX_ITEMS)
    max_runtime_seconds: int = Field(ge=1, le=900)

    @model_validator(mode="after")
    def fits_budget_and_unique_oracles(self) -> Self:
        if len(self.steps) > self.max_actions:
            raise ValueError("steps cannot exceed max_actions")
        if len(set(self.oracle_ids)) != len(self.oracle_ids):
            raise ValueError("oracle_ids must be unique")
        return self


# --- Execution results -------------------------------------------------------------------


class ActionRecord(StrictDTO):
    step_index: int = Field(ge=0)
    action: ActionKind
    outcome: Literal["ok", "error", "blocked", "skipped"]
    detail: str | None = Field(default=None, max_length=2000)
    evidence_ids: tuple[Identifier, ...] = ()


class ToolCallRecord(StrictDTO):
    tool_name: Identifier
    actor_id: Identifier
    arguments_hash: Sha256Hex
    succeeded: bool
    side_effect_ids: tuple[Identifier, ...] = ()


class Observation(StrictDTO):
    observation_id: Identifier
    attack_id: Identifier
    environment_id: Identifier
    source_sha: GitSha
    fixture_checksum: Sha256Hex
    status: Literal["completed", "aborted", "budget_exceeded", "environment_error"]
    action_log: tuple[ActionRecord, ...] = Field(max_length=MAX_ITEMS)
    tool_calls: tuple[ToolCallRecord, ...] = Field(default=(), max_length=MAX_ITEMS)
    metrics: dict[Identifier, float] = Field(default_factory=dict)
    state_hash_before: Sha256Hex | None = None
    state_hash_after: Sha256Hex | None = None
    evidence_ids: tuple[Identifier, ...] = ()
    trace_ids: tuple[Identifier, ...] = ()


class OracleVerdict(StrictDTO):
    verdict_id: Identifier
    oracle_id: OracleId
    oracle_kind: OracleKind
    criterion_version: VersionTag
    observation_id: Identifier
    outcome: OracleOutcome
    observed: str = Field(max_length=2000)
    expected: str = Field(max_length=2000)
    evidence_ids: tuple[Identifier, ...] = ()


class Finding(StrictDTO):
    finding_id: Identifier
    attack_id: Identifier
    status: GateStatus
    attribution: Attribution
    severity: Severity
    oracle_ids: tuple[OracleId, ...] = Field(min_length=1, max_length=12)
    oracle_verdict_ids: tuple[Identifier, ...] = ()
    head_reproductions: int = Field(ge=0)
    head_attempts: int = Field(ge=0)
    base_reproductions: int = Field(ge=0)
    base_attempts: int = Field(ge=0)
    evidence_ids: tuple[Identifier, ...] = ()
    trace_ids: tuple[Identifier, ...] = ()
    repro_manifest_id: Identifier | None = None
    limitations: tuple[ShortText, ...] = ()

    @model_validator(mode="after")
    def status_matches_evidence(self) -> Self:
        if self.head_reproductions > self.head_attempts:
            raise ValueError("head_reproductions exceed head_attempts")
        if self.base_reproductions > self.base_attempts:
            raise ValueError("base_reproductions exceed base_attempts")
        if self.status in CONFIRMED_GATE_STATUSES:
            if self.head_reproductions < MIN_CONFIRMING_REPRODUCTIONS:
                raise ValueError("confirmed findings need repeated head reproduction")
            if not self.oracle_verdict_ids or not self.evidence_ids:
                raise ValueError("confirmed findings need oracle verdicts and evidence")
        if self.status is GateStatus.CONFIRMED_REGRESSION and (
            self.base_attempts == 0
            or self.base_reproductions > 0
            or self.attribution is not Attribution.INTRODUCED
        ):
            raise ValueError("confirmed_regression requires a clean base run and 'introduced'")
        if self.status is GateStatus.CONFIRMED_PRE_EXISTING and (
            self.base_reproductions == 0 or self.attribution is not Attribution.PRE_EXISTING
        ):
            raise ValueError("confirmed_pre_existing requires a base failure and 'pre_existing'")
        if self.status is GateStatus.PASSED and self.head_reproductions > 0:
            raise ValueError("passed cannot have head reproductions")
        return self
