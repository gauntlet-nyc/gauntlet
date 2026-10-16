"""API view models. They wrap canonical contracts; they never redefine verdict vocabularies."""

from typing import Literal

from pydantic import BaseModel

from gauntlet.contracts import (
    ApprovalRecord,
    AttackSpec,
    AuditSummary,
    ExposureRecord,
    Finding,
    FixPlan,
    HistoricalDecision,
    LineageEdge,
    RecallVerdict,
    RemediationProposal,
    RunEvent,
    ToolEvent,
    VoiceBriefing,
)

ProvenanceMode = Literal["offline_recording", "offline_fixture", "offline_synthetic", "live"]


class Provenance(BaseModel):
    """Which provider produced an artifact. `live=False` must be shown as OFFLINE in the UI."""

    provider: str
    mode: ProvenanceMode
    live: bool
    label: str


class AttemptView(BaseModel):
    attack_id: str
    revision: Literal["base", "head"]
    attempt: int
    source_sha: str
    oracle_id: str
    outcome: str
    observed: str
    evidence_ids: list[str]
    screenshot_artifact_ids: list[str]


class FileDiff(BaseModel):
    path: str
    unified_diff: str


class FixPlanView(BaseModel):
    plan: FixPlan
    plan_sha256: str
    allowed_paths: list[str]
    provenance: Provenance


class GateRunView(BaseModel):
    run_id: str
    change_id: str
    feature_intent: str
    target_id: str
    fixture_id: str
    base_sha: str
    head_sha: str
    status: str
    attribution: str
    not_tested_reason: str | None
    diff: list[FileDiff]
    attacks: list[AttackSpec]
    rejected_attacks: list[str]
    plan_sha256: str | None
    model_id: str | None
    attempts: list[AttemptView]
    findings: list[Finding]
    fix_plan: FixPlanView | None
    events: list[RunEvent]
    provenance: list[Provenance]


class GateRunSummary(BaseModel):
    run_id: str
    change_id: str
    status: str
    attribution: str
    offline: bool


class StartGateRun(BaseModel):
    change_id: Literal["help-button", "refund-tool", "clean"] = "help-button"


class ChangeOption(BaseModel):
    change_id: str
    feature_intent: str
    base_sha: str
    head_sha: str
    offline_recording_available: bool


class DecisionView(BaseModel):
    decision: HistoricalDecision
    tool_events: list[ToolEvent]
    requester: str
    message: str


class AuditView(BaseModel):
    recall_id: str
    summary: AuditSummary
    verdicts: list[RecallVerdict]
    proposals: list[RemediationProposal]
    provenance: list[Provenance]


class CounterfactualCase(BaseModel):
    decision_id: str
    exposure: ExposureRecord
    replayable: bool
    missing_fields: list[str]
    verdict: RecallVerdict


class CounterfactualView(BaseModel):
    recall_id: str
    trigger_reference: str
    cases: list[CounterfactualCase]
    gaps: list[str]
    counts: dict[str, int]
    proposals: list[RemediationProposal]
    provenance: list[Provenance]


class LineageView(BaseModel):
    edges: list[LineageEdge]


class ReviewItem(BaseModel):
    item_id: str
    kind: Literal["remediation_proposal", "counterfactual_case"]
    recall_id: str
    title: str
    rationale: str
    classification: str
    plan_sha256: str
    status: Literal["pending", "approved_for_review", "dismissed"]
    approval_id: str | None


class ApprovalRequest(BaseModel):
    """Binds to the exact plan hash the reviewer saw. Identity comes from the bearer token."""

    run_id: str
    subject: Literal["scope", "fix_plan", "remediation"]
    subject_id: str
    plan_sha256: str
    decision: Literal["approved", "rejected"]
    reason: str | None = None


class ApprovalView(BaseModel):
    record: ApprovalRecord
    note: str


class SponsorStatus(BaseModel):
    sponsor: str
    adapter: str
    configured: bool
    missing_env: list[str]
    status: Literal["offline-tested, live NOT RUN", "live verified"]
    live_command: str
    produces: list[str]
    notes: str


class BriefingView(BaseModel):
    briefing: VoiceBriefing
    audio_available: bool
    provenance: Provenance
