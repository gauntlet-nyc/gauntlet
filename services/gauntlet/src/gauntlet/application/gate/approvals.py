"""Human approval binding (master plan Section 13).

An approval names one run, one subject, one exact SHA-256 plan hash, the target/fixture and,
for fixes, the only paths a patch may touch. It expires and can be spent once. Any edit to the
plan changes its hash, so a previous approval can never be reused for a modified patch.
"""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from gauntlet.contracts import (
    ApprovalChannel,
    ApprovalDecision,
    ApprovalRecord,
    ApprovalSubject,
    FixPlan,
)
from gauntlet.contracts.approvals import MAX_APPROVAL_TTL
from gauntlet.domain import is_patch_path_allowed
from gauntlet.ports import ApprovalStore

from ..errors import ApprovalDeniedError, StaleApprovalError

DEFAULT_APPROVAL_TTL = timedelta(hours=2)


def fix_plan_hash(plan: FixPlan) -> str:
    """Hash of everything that determines what a patch run does (creation time excluded)."""
    document = plan.model_dump(mode="json", exclude={"created_at"})
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AuthenticatedReviewer:
    """Produced by the API auth layer (C); never parsed from a request body."""

    reviewer_id: str
    channel: ApprovalChannel


@dataclass(frozen=True)
class ApprovalScope:
    run_id: str
    target_id: str
    fixture_id: str
    current_plan_sha256: str
    allowed_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExecutionRequest:
    """What an executor is about to do, with the hash it computed from the actual plan/diff."""

    run_id: str
    subject: ApprovalSubject
    subject_id: str
    plan_sha256: str
    target_id: str
    fixture_id: str
    touched_paths: tuple[str, ...] = ()


def approval_mismatches(
    record: ApprovalRecord, request: ExecutionRequest, now: datetime
) -> tuple[str, ...]:
    reasons: list[str] = []
    if record.decision != "approved":
        reasons.append("approval was rejected")
    if now >= record.expires_at:
        reasons.append("approval has expired")
    for field in ("run_id", "subject", "subject_id", "plan_sha256", "target_id", "fixture_id"):
        if getattr(record, field) != getattr(request, field):
            reasons.append(f"{field} does not match the approval")
    if record.subject == "fix_plan":
        allowed = set(record.allowed_paths)
        outside = sorted(p for p in request.touched_paths if p not in allowed)
        if outside:
            reasons.append(f"patch touches unapproved paths: {', '.join(outside[:5])}")
        if any(not is_patch_path_allowed(p) for p in request.touched_paths):
            reasons.append("patch touches protected paths")
    elif request.touched_paths:
        reasons.append(f"{record.subject} approvals do not authorize file changes")
    return tuple(reasons)


class ApprovalService:
    def __init__(
        self,
        store: ApprovalStore,
        clock: Callable[[], datetime],
        new_approval_id: Callable[[], str],
        ttl: timedelta = DEFAULT_APPROVAL_TTL,
    ) -> None:
        if not timedelta(0) < ttl <= MAX_APPROVAL_TTL:
            raise ValueError("approval TTL must be positive and at most 24 hours")
        self._store = store
        self._clock = clock
        self._new_id = new_approval_id
        self._ttl = ttl

    async def record(
        self, scope: ApprovalScope, decision: ApprovalDecision, reviewer: AuthenticatedReviewer
    ) -> ApprovalRecord:
        if decision.plan_sha256 != scope.current_plan_sha256:
            raise StaleApprovalError("the plan changed after it was reviewed; review it again")
        decided_at = self._clock()
        approved_fix = decision.subject == "fix_plan" and decision.decision == "approved"
        record = ApprovalRecord(
            approval_id=self._new_id(),
            run_id=scope.run_id,
            subject=decision.subject,
            subject_id=decision.subject_id,
            plan_sha256=decision.plan_sha256,
            decision=decision.decision,
            reviewer_id=reviewer.reviewer_id,
            channel=reviewer.channel,
            decided_at=decided_at,
            expires_at=decided_at + self._ttl,
            target_id=scope.target_id,
            fixture_id=scope.fixture_id,
            allowed_paths=scope.allowed_paths if approved_fix else (),
            reason=decision.reason,
        )
        await self._store.save(record)
        return record

    async def authorize(self, approval_id: str, request: ExecutionRequest) -> ApprovalRecord:
        """Check and spend an approval. Raise ApprovalDeniedError on any mismatch."""
        record = await self._store.get(approval_id)
        if record is None:
            raise ApprovalDeniedError(("approval does not exist",))
        reasons = approval_mismatches(record, request, self._clock())
        if reasons:
            raise ApprovalDeniedError(reasons)
        await self._store.consume(approval_id, f"{request.run_id}:{request.subject_id}")
        return record
