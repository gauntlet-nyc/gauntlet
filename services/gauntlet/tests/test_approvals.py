"""Approvals bind to an exact plan hash, expire, are single-use and never cover protected paths."""

import asyncio
import itertools
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fakes import InMemoryApprovalStore
from pydantic import ValidationError

from gauntlet.application import ApprovalDeniedError, StaleApprovalError
from gauntlet.application.gate import (
    ApprovalScope,
    ApprovalService,
    AuthenticatedReviewer,
    ExecutionRequest,
    fix_plan_hash,
)
from gauntlet.contracts import ApprovalDecision, ApprovalRecord, FixPlan
from gauntlet.domain import is_patch_path_allowed
from gauntlet.ports import ApprovalAlreadyConsumedError

EXAMPLES = Path(__file__).resolve().parents[3] / "docs" / "contracts" / "examples"
T0 = datetime(2026, 10, 14, 15, 0, tzinfo=UTC)
HELP = "web/src/components/FloatingHelp.tsx"
REVIEWER = AuthenticatedReviewer(reviewer_id="reviewer-rudra", channel="dashboard")


def load(name: str) -> dict[str, object]:
    data: dict[str, object] = json.loads((EXAMPLES / name).read_text(encoding="utf-8"))
    return data


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


def setup() -> tuple[ApprovalService, InMemoryApprovalStore, Clock, FixPlan, str]:
    store = InMemoryApprovalStore()
    clock = Clock()
    ids = (f"approval-{n}" for n in itertools.count(1))
    service = ApprovalService(store, clock, lambda: next(ids), ttl=timedelta(hours=2))
    plan = FixPlan.model_validate(load("fix-plan.v1.json"))
    return service, store, clock, plan, fix_plan_hash(plan)


def scope(plan_hash: str) -> ApprovalScope:
    return ApprovalScope(
        run_id="run-001",
        target_id="cartwheel-fixture",
        fixture_id="baseline-v1",
        current_plan_sha256=plan_hash,
        allowed_paths=(HELP,),
    )


def approve(service: ApprovalService, plan_hash: str) -> ApprovalRecord:
    decision = ApprovalDecision(
        subject="fix_plan", subject_id="fix-001", plan_sha256=plan_hash, decision="approved"
    )
    return asyncio.run(service.record(scope(plan_hash), decision, REVIEWER))


def request(plan_hash: str, **overrides: object) -> ExecutionRequest:
    base = ExecutionRequest(
        run_id="run-001",
        subject="fix_plan",
        subject_id="fix-001",
        plan_sha256=plan_hash,
        target_id="cartwheel-fixture",
        fixture_id="baseline-v1",
        touched_paths=(HELP,),
    )
    return replace(base, **overrides)  # type: ignore[arg-type]


def denied_reasons(service: ApprovalService, approval_id: str, req: ExecutionRequest) -> str:
    with pytest.raises(ApprovalDeniedError) as info:
        asyncio.run(service.authorize(approval_id, req))
    return str(info.value)


def test_golden_approval_hash_matches_golden_fix_plan() -> None:
    _, _, _, _, plan_hash = setup()
    assert load("approval-record.v1.json")["plan_sha256"] == plan_hash


def test_matching_request_is_authorized_once() -> None:
    service, store, _, _, plan_hash = setup()
    record = approve(service, plan_hash)
    assert asyncio.run(service.authorize(record.approval_id, request(plan_hash))) == record
    assert store.consumed == {record.approval_id: "run-001:fix-001"}
    with pytest.raises(ApprovalAlreadyConsumedError):
        asyncio.run(service.authorize(record.approval_id, request(plan_hash)))


def test_modified_patch_cannot_reuse_approval() -> None:
    service, _, _, plan, plan_hash = setup()
    record = approve(service, plan_hash)
    tampered = plan.model_copy(update={"unified_diff": plan.unified_diff + "+// sneaky\n"})
    reasons = denied_reasons(service, record.approval_id, request(fix_plan_hash(tampered)))
    assert "plan_sha256 does not match" in reasons


def test_approving_a_stale_plan_hash_is_refused() -> None:
    service, _, _, _, plan_hash = setup()
    decision = ApprovalDecision(
        subject="fix_plan", subject_id="fix-001", plan_sha256="0" * 64, decision="approved"
    )
    with pytest.raises(StaleApprovalError):
        asyncio.run(service.record(scope(plan_hash), decision, REVIEWER))


def test_expired_approval_is_denied() -> None:
    service, _, clock, _, plan_hash = setup()
    record = approve(service, plan_hash)
    clock.now = T0 + timedelta(hours=2)
    assert "expired" in denied_reasons(service, record.approval_id, request(plan_hash))


def test_rejected_approval_never_authorizes() -> None:
    service, _, _, _, plan_hash = setup()
    decision = ApprovalDecision(
        subject="fix_plan",
        subject_id="fix-001",
        plan_sha256=plan_hash,
        decision="rejected",
        reason="hides Help on mobile",
    )
    record = asyncio.run(service.record(scope(plan_hash), decision, REVIEWER))
    assert record.allowed_paths == ()
    assert "rejected" in denied_reasons(service, record.approval_id, request(plan_hash))


@pytest.mark.parametrize(
    ("override", "expected"),
    [
        ({"run_id": "run-002"}, "run_id"),
        ({"target_id": "prod-shop"}, "target_id"),
        ({"fixture_id": "other"}, "fixture_id"),
        ({"touched_paths": (HELP, "web/src/app/checkout/page.tsx")}, "unapproved paths"),
        ({"touched_paths": ("web/src/components/FloatingHelp.test.tsx",)}, "protected paths"),
    ],
)
def test_any_scope_mismatch_is_denied(override: dict[str, object], expected: str) -> None:
    service, _, _, _, plan_hash = setup()
    record = approve(service, plan_hash)
    assert expected in denied_reasons(service, record.approval_id, request(plan_hash, **override))


def test_scope_approval_cannot_authorize_file_changes() -> None:
    service, _, _, _, plan_hash = setup()
    decision = ApprovalDecision(
        subject="scope", subject_id="run-001", plan_sha256=plan_hash, decision="approved"
    )
    record = asyncio.run(
        service.record(replace(scope(plan_hash), allowed_paths=()), decision, REVIEWER)
    )
    req = request(plan_hash, subject="scope", subject_id="run-001")
    assert "do not authorize file changes" in denied_reasons(service, record.approval_id, req)


def test_unknown_approval_is_denied() -> None:
    service, _, _, _, plan_hash = setup()
    assert "does not exist" in denied_reasons(service, "approval-404", request(plan_hash))


@pytest.mark.parametrize(
    "path",
    [
        "tests/checkout.spec.ts",
        "web/src/a.test.tsx",
        "services/x/test_oracle.py",
        "src/verification/ui_oracles.py",
        "bench/public/README.md",
        ".github/workflows/ci.yml",
        "pnpm-lock.yaml",
        ".env",
        # case variants reach the same files on case-insensitive filesystems
        "TESTS/checkout.spec.ts",
        "web/src/a.Test.TSX",
        "src/Verification/ui_oracles.py",
        "Oracles/x.py",
        "BENCH/public/README.md",
        ".GITHUB/workflows/ci.yml",
        "UV.LOCK",
        "package-lock.JSON",
        ".ENV",
        ".Env.local",
    ],
)
def test_fix_plans_cannot_target_protected_paths(path: str) -> None:
    assert not is_patch_path_allowed(path)
    with pytest.raises(ValidationError):
        FixPlan.model_validate({**load("fix-plan.v1.json"), "allowed_paths": [path]})


def test_voice_channel_and_long_ttl_are_impossible() -> None:
    record = load("approval-record.v1.json")
    with pytest.raises(ValidationError):
        ApprovalRecord.model_validate({**record, "channel": "voice"})
    with pytest.raises(ValidationError):
        ApprovalRecord.model_validate({**record, "expires_at": "2026-10-16T15:05:00Z"})
    with pytest.raises(ValueError, match="TTL"):
        ApprovalService(InMemoryApprovalStore(), Clock(), lambda: "a", ttl=timedelta(days=2))


def test_rejection_requires_reason() -> None:
    with pytest.raises(ValidationError):
        ApprovalDecision.model_validate(
            {**load("approval-decision.v1.json"), "decision": "rejected", "reason": None}
        )
