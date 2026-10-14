"""Recall DTOs for historical audit and counterfactual decision analysis."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from .common import StrictDTO


class HistoricalDecision(StrictDTO):
    decision_id: str = Field(min_length=1)
    occurred_at: datetime
    model_id: str
    prompt_version: str
    policy_version: str
    tool_results_hash: str | None = None
    kb_snapshot_hash: str | None = None
    memory_snapshot_hash: str | None = None
    structured_action: str
    amount_minor: int | None = None
    source_ids: tuple[str, ...] = ()
    missing_inputs: tuple[str, ...] = ()


class RecallTrigger(StrictDTO):
    trigger_id: str = Field(min_length=1)
    kind: Literal["finding", "document", "memory", "model_version", "prompt_version", "policy_version", "tool_result_window"]
    reference: str = Field(min_length=1)
    mode: Literal["event_audit", "decision_counterfactual"]
    start_at: datetime
    end_at: datetime
    target_id: str


RecallClassification = Literal[
    "audit_violation", "audit_clear", "tainted", "cleared", "inconclusive", "not_replayable"
]


class RecallVerdict(StrictDTO):
    verdict_id: str
    recall_id: str
    decision_id: str
    classification: RecallClassification
    control_matches: bool | None = None
    material_change: bool | None = None
    evidence_ids: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
