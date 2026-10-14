"""Recall DTOs for historical audit and counterfactual decision analysis."""

from typing import Literal, Self

from pydantic import Field, model_validator

from gauntlet.domain import RecallClassification

from .common import (
    MAX_ITEMS,
    Identifier,
    MissingInput,
    Sha256Hex,
    ShortText,
    StrictDTO,
    UtcDatetime,
    VersionTag,
)

RecallMode = Literal["event_audit", "decision_counterfactual"]

_AUDIT_CLASSES = frozenset({RecallClassification.AUDIT_VIOLATION, RecallClassification.AUDIT_CLEAR})


class HistoricalDecision(StrictDTO):
    decision_id: Identifier
    occurred_at: UtcDatetime
    agent_id: Identifier
    actor_ref: Identifier
    model_id: Identifier
    prompt_version: VersionTag
    policy_version: VersionTag
    tool_names: tuple[Identifier, ...] = ()
    tool_results_hash: Sha256Hex | None = None
    kb_snapshot_hash: Sha256Hex | None = None
    memory_snapshot_hash: Sha256Hex | None = None
    structured_action: Identifier
    amount_minor: int | None = Field(default=None, ge=0)
    source_ids: tuple[Identifier, ...] = Field(default=(), max_length=MAX_ITEMS)
    missing_inputs: tuple[MissingInput, ...] = ()


class RecallTrigger(StrictDTO):
    trigger_id: Identifier
    kind: Literal[
        "finding",
        "document",
        "memory",
        "model_version",
        "prompt_version",
        "policy_version",
        "tool_result_window",
    ]
    reference: str = Field(min_length=1, max_length=512)
    mode: RecallMode
    start_at: UtcDatetime
    end_at: UtcDatetime
    target_id: Identifier

    @model_validator(mode="after")
    def window_ordered(self) -> Self:
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        return self


class RecallVerdict(StrictDTO):
    verdict_id: Identifier
    recall_id: Identifier
    decision_id: Identifier
    mode: RecallMode
    classification: RecallClassification
    rationale: ShortText
    criterion_version: VersionTag
    control_matches: bool | None = None
    material_change: bool | None = None
    replay_ids: tuple[Identifier, ...] = ()
    evidence_ids: tuple[Identifier, ...] = ()
    limitations: tuple[ShortText, ...] = ()

    @model_validator(mode="after")
    def classification_matches_mode_and_evidence(self) -> Self:
        cls = self.classification
        if self.mode == "event_audit":
            if cls in (RecallClassification.TAINTED, RecallClassification.CLEARED):
                raise ValueError("event_audit cannot produce counterfactual classifications")
            if self.control_matches is not None or self.material_change is not None:
                raise ValueError("event_audit verdicts carry no replay control fields")
            if cls is RecallClassification.AUDIT_VIOLATION and not self.evidence_ids:
                raise ValueError("audit_violation requires authoritative evidence")
            return self
        if cls in _AUDIT_CLASSES:
            raise ValueError("decision_counterfactual cannot produce audit classifications")
        if cls is RecallClassification.TAINTED and not (
            self.control_matches is True and self.material_change is True and self.replay_ids
        ):
            raise ValueError("tainted requires a matching control, material change and replays")
        if cls is RecallClassification.CLEARED and not (
            self.control_matches is True and self.material_change is False and self.replay_ids
        ):
            raise ValueError("cleared requires a matching control, no material change and replays")
        return self
