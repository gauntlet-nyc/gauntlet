from dataclasses import replace
from pathlib import Path

import pytest
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


def test_configured_ui_run_has_executable_plan_but_requires_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    from gauntlet.api.container import get_container
    from gauntlet.api.main import app
    from gauntlet.api.settings import get_settings

    modules = tmp_path / "node_modules"
    cli = modules / "next/dist/bin/next"
    cli.parent.mkdir(parents=True)
    cli.write_text("// no execution before approval")
    monkeypatch.setenv("GAUNTLET_UI_REPAIR_NODE_MODULES", str(modules))
    monkeypatch.setenv("RUN_LIVE_INTEGRATIONS", "0")
    monkeypatch.setenv("GAUNTLET_MODEL_PROVIDER", "scripted")
    monkeypatch.setenv("GAUNTLET_REVIEWER_TOKENS", "reviewer:test-token-1234567890")
    get_container.cache_clear()
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            result = client.post("/gate/runs", json={"change_id": "help-button"})
            assert result.status_code == 201
            run = result.json()
            assert run["status"] == "confirmed_regression"
            assert run["fix_plan"]["repairable"] is True
            assert "+  bottom: 96px;" in run["fix_plan"]["plan"]["unified_diff"]
            denied = client.post(
                f"/gate/runs/{run['run_id']}/repair",
                headers={"Authorization": "Bearer test-token-1234567890"},
            )
            assert denied.status_code == 409
            assert "approve the fix plan hash" in denied.json()["detail"]
    finally:
        get_container.cache_clear()
        get_settings.cache_clear()


def test_executor_environment_failure_returns_not_verified(tmp_path: Path) -> None:
    from gauntlet.application.gate.repair import RepairUseCase
    from gauntlet.ports import EnvironmentUnavailableError

    async def run(
        repair: RepairRuntime, plan: FixPlan, plan_hash: str, attack: AttackSpec, target: GateTarget
    ) -> None:
        class UnavailableExecutor:
            collector = "browser_collector"

            async def attempt(self, *args: object) -> None:
                raise EnvironmentUnavailableError("browser unavailable")

        use_case = RepairUseCase(replace(repair.use_case._deps, executor=UnavailableExecutor()))
        approval_id = await approve(repair, plan, plan_hash, target)
        report = await use_case.execute(
            approval_id,
            plan,
            target_id=target.target_id,
            fixture_id=target.fixture_id,
            fixture_checksum=target.fixture_checksum,
            suite=refund_verification_suite(target, attack),
        )
        assert report.verdict is ReleaseVerdict.NOT_VERIFIED
        assert report.checks[0].detail.startswith("environment")

    scenario(tmp_path, run)
