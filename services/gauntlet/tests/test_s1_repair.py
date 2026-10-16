"""P3 repair: approval binds to the exact plan hash, patch runs isolated, fix is re-verified."""

import asyncio
import shutil
import subprocess
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest

from gauntlet.application.errors import ApprovalDeniedError
from gauntlet.application.gate import ApprovalScope, AuthenticatedReviewer
from gauntlet.application.gate.repair import ReleaseVerdict, RepairReport, diff_paths
from gauntlet.composition import (
    GateTarget,
    RepairRuntime,
    build_gate,
    build_repair,
    refund_verification_suite,
)
from gauntlet.contracts import ApprovalDecision, AttackSpec, FixPlan
from gauntlet.ports import ApprovalAlreadyConsumedError
from gauntlet.settings import Settings

ROOT = Path(__file__).resolve().parents[3]
REVIEWER = AuthenticatedReviewer(reviewer_id="alice", channel="dashboard")
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is required")

Step = Callable[[RepairRuntime, FixPlan, str, AttackSpec, GateTarget], Awaitable[object]]


def build_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "cartwheel"
    subprocess.run(
        [sys.executable, "scripts/build_cartwheel_refund_fixture.py", "--dest", str(repo)],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return repo


async def approve(repair: RepairRuntime, plan: FixPlan, plan_hash: str, target: GateTarget) -> str:
    record = await repair.approvals.record(
        ApprovalScope(
            run_id=plan.run_id,
            target_id=target.target_id,
            fixture_id=target.fixture_id,
            current_plan_sha256=plan_hash,
            allowed_paths=plan.allowed_paths,
        ),
        ApprovalDecision(
            subject="fix_plan",
            subject_id=plan.fix_plan_id,
            plan_sha256=plan_hash,
            decision="approved",
        ),
        REVIEWER,
    )
    return record.approval_id


def scenario(tmp_path: Path, step: Step) -> object:
    target = GateTarget.cartwheel_refund(build_repo(tmp_path))
    settings = Settings.from_env({})

    async def go() -> object:
        gate = await build_gate(
            settings, target, model="scripted", sandbox="fake", browser="fake",
            artifact_root=tmp_path / "evidence",
        )  # fmt: skip
        try:
            change = target.change(intent="refund")
            report = await gate.use_case.execute("run-fix", change, target.fixture_checksum)
            outcome = report.outcomes[0]
            repair = build_repair(settings, target, gate, model="scripted")
            plan, plan_hash = await repair.use_case.propose(
                "run-fix", outcome.finding, outcome.attack, change.head_sha
            )
            return await step(repair, plan, plan_hash, outcome.attack, target)
        finally:
            await gate.aclose()

    return asyncio.run(go())


async def _execute(
    repair: RepairRuntime, plan: FixPlan, approval_id: str, attack: AttackSpec, target: GateTarget
) -> RepairReport:
    return await repair.use_case.execute(
        approval_id,
        plan,
        target_id=target.target_id,
        fixture_id=target.fixture_id,
        fixture_checksum=target.fixture_checksum,
        suite=refund_verification_suite(target, attack),
    )


def test_approved_fix_is_verified_for_review_only(tmp_path: Path) -> None:
    async def step(
        repair: RepairRuntime,
        plan: FixPlan,
        plan_hash: str,
        attack: AttackSpec,
        target: GateTarget,
    ) -> object:
        approval_id = await approve(repair, plan, plan_hash, target)
        report = await _execute(repair, plan, approval_id, attack, target)
        with pytest.raises((ApprovalDeniedError, ApprovalAlreadyConsumedError)):  # single use
            await _execute(repair, plan, approval_id, attack, target)
        return report

    report = scenario(tmp_path, step)
    assert isinstance(report, RepairReport)
    assert report.verdict is ReleaseVerdict.FIX_VERIFIED_REVIEW_REQUIRED
    assert report.patched_sha and report.touched_paths == ("api/src/tools/request_refund.ts",)
    assert {c.name for c in report.checks} == {
        "original_attack",
        "variant_0",
        "legitimate_workflow",
    }
    assert all(c.passed for c in report.checks)


def test_edited_plan_cannot_reuse_the_approval(tmp_path: Path) -> None:
    async def step(
        repair: RepairRuntime,
        plan: FixPlan,
        plan_hash: str,
        attack: AttackSpec,
        target: GateTarget,
    ) -> object:
        approval_id = await approve(repair, plan, plan_hash, target)
        edited = plan.model_copy(update={"unified_diff": plan.unified_diff + "\n"})
        with pytest.raises(ApprovalDeniedError):
            await _execute(repair, edited, approval_id, attack, target)
        return True

    assert scenario(tmp_path, step) is True


def test_fix_that_disables_the_feature_is_rejected(tmp_path: Path) -> None:
    async def step(
        repair: RepairRuntime,
        plan: FixPlan,
        plan_hash: str,
        attack: AttackSpec,
        target: GateTarget,
    ) -> object:
        broken = plan.model_copy(
            update={
                "unified_diff": plan.unified_diff.replace(
                    "+  if (order.ownerId !== ctx.actorId) {",
                    "+  if (true) {",
                )
            }
        )
        from gauntlet.application.gate import fix_plan_hash

        approval_id = await approve(repair, broken, fix_plan_hash(broken), target)
        return await _execute(repair, broken, approval_id, attack, target)

    report = scenario(tmp_path, step)
    assert isinstance(report, RepairReport)
    assert report.verdict is ReleaseVerdict.FIX_REJECTED
    legit = next(c for c in report.checks if c.name == "legitimate_workflow")
    assert not legit.passed


def test_diff_paths_refuses_unsafe_patches() -> None:
    with pytest.raises(ValueError):
        diff_paths("diff --git a/x b/x\nGIT binary patch\n")
    with pytest.raises(ValueError):
        diff_paths("no paths here")
    assert diff_paths("--- a/src/a.ts\n+++ b/src/a.ts\n@@ -1 +1 @@\n-x\n+y\n") == ("src/a.ts",)
