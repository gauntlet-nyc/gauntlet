from dataclasses import replace
from pathlib import Path

from test_s1_repair import approve, scenario

from gauntlet.application.gate.repair import CheckResult, ReleaseVerdict
from gauntlet.composition import GateTarget, RepairRuntime, refund_verification_suite
from gauntlet.contracts import AttackSpec, FixPlan
from gauntlet.ports import EnvironmentHandle


def test_feature_checks_can_reject_an_otherwise_passing_repair(tmp_path: Path) -> None:
    async def run(
        repair: RepairRuntime, plan: FixPlan, plan_hash: str, attack: AttackSpec, target: GateTarget
    ) -> None:
        approval_id = await approve(repair, plan, plan_hash, target)

        async def broken_feature(environment: EnvironmentHandle) -> tuple[CheckResult, ...]:
            return (CheckResult("help_dialog", False, "Help no longer opens"),)

        suite = replace(refund_verification_suite(target, attack), feature_checks=broken_feature)
        report = await repair.use_case.execute(
            approval_id,
            plan,
            target_id=target.target_id,
            fixture_id=target.fixture_id,
            fixture_checksum=target.fixture_checksum,
            suite=suite,
        )
        assert report.verdict is ReleaseVerdict.FIX_REJECTED
        assert report.checks[-1].name == "help_dialog"

    scenario(tmp_path, run)
