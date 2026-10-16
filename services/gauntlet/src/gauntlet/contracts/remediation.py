"""Recall outputs for humans: audit counts from records, and remediation *drafts*.

Every remediation action is a review request. There is no 'executed' status: Gauntlet never
reverses a transaction, contacts a customer or changes production on its own.
"""

from typing import Literal, Self

from pydantic import Field, model_validator

from .common import Identifier, ShortText, StrictDTO, UtcDatetime

RemediationAction = Literal[
    "reverse_transaction_review",
    "customer_contact_review",
    "collect_missing_evidence",
    "policy_fix_review",
]


class AuditSummary(StrictDTO):
    """Counts computed from verdict records; never typed in by hand or by a model."""

    recall_id: Identifier
    tool_name: Identifier
    start_at: UtcDatetime
    end_at: UtcDatetime
    audited: int = Field(ge=0)
    violations: int = Field(ge=0)
    clear: int = Field(ge=0)
    inconclusive: int = Field(ge=0)
    gaps: tuple[ShortText, ...] = ()

    @model_validator(mode="after")
    def counts_add_up(self) -> Self:
        if self.violations + self.clear + self.inconclusive != self.audited:
            raise ValueError("violations + clear + inconclusive must equal audited")
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        return self


class RemediationProposal(StrictDTO):
    proposal_id: Identifier
    recall_id: Identifier
    action: RemediationAction
    verdict_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=500)
    affected_actor_refs: tuple[Identifier, ...] = Field(default=(), max_length=500)
    rationale: ShortText
    evidence_ids: tuple[Identifier, ...] = ()
    status: Literal["draft", "approved_for_review", "dismissed"] = "draft"
    created_at: UtcDatetime
