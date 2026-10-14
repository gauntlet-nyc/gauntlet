"""Fix plans and human approvals. An approval binds to one exact plan hash and is single-use."""

from datetime import timedelta
from typing import Annotated, Final, Literal, Self

from pydantic import AfterValidator, Field, model_validator

from gauntlet.domain import is_patch_path_allowed

from .common import (
    MAX_TEXT,
    GitSha,
    Identifier,
    RelativePath,
    Sha256Hex,
    ShortText,
    StrictDTO,
    UtcDatetime,
)

MAX_APPROVAL_TTL: Final = timedelta(hours=24)

ApprovalSubject = Literal["scope", "fix_plan", "remediation"]
ApprovalChannel = Literal["dashboard", "api"]
"""Voice is deliberately absent: a spoken utterance can never approve anything."""


def _require_patchable(path: str) -> str:
    if not is_patch_path_allowed(path):
        raise ValueError("path is protected (tests, oracles, benchmark, CI, locks or secrets)")
    return path


PatchPath = Annotated[RelativePath, AfterValidator(_require_patchable)]


class FixPlan(StrictDTO):
    fix_plan_id: Identifier
    run_id: Identifier
    finding_id: Identifier
    base_sha: GitSha
    allowed_paths: tuple[PatchPath, ...] = Field(min_length=1, max_length=50)
    unified_diff: str = Field(min_length=1, max_length=200_000)
    rationale: ShortText
    test_plan: tuple[ShortText, ...] = Field(min_length=1, max_length=20)
    created_at: UtcDatetime


class ApprovalDecision(StrictDTO):
    """What an authenticated reviewer submits. Reviewer identity comes from auth, not the body."""

    subject: ApprovalSubject
    subject_id: Identifier
    plan_sha256: Sha256Hex
    decision: Literal["approved", "rejected"]
    reason: str | None = Field(default=None, max_length=MAX_TEXT)

    @model_validator(mode="after")
    def rejection_has_reason(self) -> Self:
        if self.decision == "rejected" and not self.reason:
            raise ValueError("a rejection must state a reason")
        return self


class ApprovalRecord(StrictDTO):
    approval_id: Identifier
    run_id: Identifier
    subject: ApprovalSubject
    subject_id: Identifier
    plan_sha256: Sha256Hex
    decision: Literal["approved", "rejected"]
    reviewer_id: Identifier
    channel: ApprovalChannel
    decided_at: UtcDatetime
    expires_at: UtcDatetime
    target_id: Identifier
    fixture_id: Identifier
    allowed_paths: tuple[PatchPath, ...] = Field(default=(), max_length=50)
    reason: str | None = Field(default=None, max_length=MAX_TEXT)

    @model_validator(mode="after")
    def bounded_and_scoped(self) -> Self:
        if not self.decided_at < self.expires_at <= self.decided_at + MAX_APPROVAL_TTL:
            raise ValueError("expires_at must be after decided_at and within 24 hours")
        if self.subject == "fix_plan" and self.decision == "approved" and not self.allowed_paths:
            raise ValueError("an approved fix plan must list allowed_paths")
        if self.subject != "fix_plan" and self.allowed_paths:
            raise ValueError("only fix_plan approvals carry allowed_paths")
        return self
