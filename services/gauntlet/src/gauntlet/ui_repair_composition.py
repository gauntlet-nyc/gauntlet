"""Repair registered Cartwheel UI revisions with real, explicitly local browser checks."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast
from uuid import uuid4

from gauntlet.application.gate import ApprovalService
from gauntlet.application.gate.attempts import OracleAttemptExecutor
from gauntlet.application.gate.pair_verdict import GateAttempt
from gauntlet.application.gate.repair import (
    CheckResult,
    RepairDependencies,
    RepairUseCase,
    VerificationSuite,
)
from gauntlet.composition import GateRuntime, GateTarget, RepairRuntime, build_model_gateway
from gauntlet.contracts import AttackSpec, EvidenceSubject, ResizeStep
from gauntlet.integrations.browser_evidence import BrowserEvidenceCollector
from gauntlet.integrations.fake.approvals import InMemoryApprovalStore
from gauntlet.integrations.fix_proposers import ModelFixProposer, ScriptedUiFixProposer
from gauntlet.integrations.local_browser import LocalBrowserProvider, PlaywrightBrowser
from gauntlet.integrations.patch_runner import GitWorktreePatchRunner
from gauntlet.integrations.ui_repair_checks import check_ui_features
from gauntlet.integrations.ui_repair_sandbox import LocalUIRepairSandbox
from gauntlet.ports import (
    ArtifactStore,
    EnvironmentHandle,
    EnvironmentUnavailableError,
    SandboxProvider,
)
from gauntlet.settings import ModelProvider, Settings
from gauntlet.verification.registry import RegisteredOracleRegistry
from gauntlet.verification.stored_browser import StoredBrowserOracle
from gauntlet.workers.ui import UIWorker


class LocalRepairExecutor:
    @property
    def collector(self) -> Literal["browser_collector"]:
        return "browser_collector"

    def __init__(self, artifacts: ArtifactStore, chromium: str | None) -> None:
        self.artifacts = artifacts
        self.chromium = chromium
        self.attempts: list[GateAttempt] = []

    async def attempt(
        self, attack: AttackSpec, environment: EnvironmentHandle, subject: EvidenceSubject
    ) -> GateAttempt:
        from playwright.async_api import Error, async_playwright

        async with async_playwright() as pw:
            try:
                browser = await pw.chromium.launch(executable_path=self.chromium, headless=True)
            except Error as exc:
                raise EnvironmentUnavailableError("local repair browser unavailable") from exc
            try:
                provider = LocalBrowserProvider(
                    cast(PlaywrightBrowser, browser), BrowserEvidenceCollector(self.artifacts)
                )
                targets = {environment.target_id: "checkout-primary-action"}
                oracle = StoredBrowserOracle(self.artifacts, primary_targets=targets)
                registry = RegisteredOracleRegistry(
                    plans=(attack,), primary_targets=targets, evidence=()
                )
                executor = OracleAttemptExecutor(
                    UIWorker(provider, registry), oracle, self.artifacts
                )
                result = await executor.attempt(attack, environment, subject)
                self.attempts.append(result)
                return result
            finally:
                await browser.close()


def build_ui_repair(
    settings: Settings, target: GateTarget, gate: GateRuntime, *, model: ModelProvider
) -> RepairRuntime:
    if target.target_id != "cartwheel-fixture" or target.has_agent_tool:
        raise ValueError("UI repair supports only the registered Cartwheel UI fixture")
    modules = Path(settings.require("GAUNTLET_UI_REPAIR_NODE_MODULES"))
    if not (modules / "next/dist/bin/next").is_file():
        raise ValueError("GAUNTLET_UI_REPAIR_NODE_MODULES must contain built fixture dependencies")
    now = datetime.now(UTC)
    if model == "scripted":
        proposer = ScriptedUiFixProposer(target.repository_path, now)
        proposer_label = "offline_scripted_fix"
    else:
        gateway, proposer_label = build_model_gateway(model, settings, target)
        proposer = ModelFixProposer(gateway, target.repository_path, now)  # type: ignore[assignment]
    sandbox = LocalUIRepairSandbox(
        target.repository_path,
        target_id=target.target_id,
        fixture_id=target.fixture_id,
        fixture_checksum=target.fixture_checksum,
        head_sha=target.head_sha,
        dependency_cache=modules,
    )

    def sandbox_for(head_sha: str, patched_sha: str) -> SandboxProvider:
        if head_sha != target.head_sha:
            raise ValueError("repair head differs from registered fixture")
        sandbox.allow(patched_sha)
        return sandbox

    executor = LocalRepairExecutor(gate.artifacts, settings.optional("GAUNTLET_CHROMIUM_PATH"))
    approvals = ApprovalService(
        InMemoryApprovalStore(), lambda: datetime.now(UTC), lambda: f"approval-{uuid4().hex}"
    )
    use_case = RepairUseCase(
        RepairDependencies(
            proposer=proposer,
            approvals=approvals,
            runner=GitWorktreePatchRunner(target.repository_path),
            executor=executor,
            sandbox_for=sandbox_for,
            clock=lambda: datetime.now(UTC),
            new_id=lambda prefix: f"{prefix}-{uuid4().hex}",
        )
    )
    return RepairRuntime(
        use_case,
        approvals,
        {
            "proposer": proposer_label,
            "patch_runner": "local_git_worktree",
            "approval_store": "in_memory",
            "browser": "local_headless_chromium",
            "sandbox": "local_ui_rebuild",
        },
        attempts=executor.attempts,
    )


def ui_verification_suite(original: AttackSpec, settings: Settings) -> VerificationSuite:
    if original.worker_kind != "ui":
        raise ValueError("UI repair requires a UI attack")
    variants = tuple(
        original.model_copy(
            update={
                "attack_id": f"{original.attack_id}-width-{width}",
                "steps": tuple(
                    ResizeStep(width=width, height=812) if isinstance(s, ResizeStep) else s
                    for s in original.steps
                ),
            }
        )
        for width in (390, 1280)
    )

    async def features(environment: EnvironmentHandle) -> tuple[CheckResult, ...]:
        return await check_ui_features(
            environment, chromium_path=settings.optional("GAUNTLET_CHROMIUM_PATH")
        )

    return VerificationSuite(
        original=original,
        variants=variants,
        legitimate=original,
        legitimate_ok=lambda obs: obs.status == "completed",
        feature_checks=features,
    )
