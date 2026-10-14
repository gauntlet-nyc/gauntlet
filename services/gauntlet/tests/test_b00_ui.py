"""Golden UI execution, evidence binding, and failure/cleanup behavior."""

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest
from gauntlet.contracts import ActionRecord, AttackSpec, Observation
from gauntlet.contracts.gate import ActionStep, ChatStep, NavigateStep
from gauntlet.integrations.fake.browser import BrowserRecording, FakeBrowserProvider
from gauntlet.integrations.fake.sandbox import FakeSandboxProvider, Fixture
from gauntlet.ports.errors import EnvironmentUnavailableError, UnknownOracleError
from gauntlet.ports.sandbox import EnvironmentHandle
from gauntlet.verification.registry import ClickEvidence, RegisteredOracleRegistry
from gauntlet.workers.ui import UIWorker

GOLDENS = Path(__file__).resolve().parents[3] / "docs/contracts/examples"


def plan() -> AttackSpec:
    return AttackSpec.model_validate_json((GOLDENS / "ui-plan.v1.json").read_text())


def observation() -> Observation:
    return Observation.model_validate_json((GOLDENS / "observation.v1.json").read_text())


def environment() -> EnvironmentHandle:
    obs = observation()
    return EnvironmentHandle(
        obs.environment_id,
        plan().target_id,
        obs.source_sha,
        plan().fixture_id,
        obs.fixture_checksum,
        "https://fake-preview.invalid",
    )


def recording() -> BrowserRecording:
    return BrowserRecording(
        plan(), environment().source_sha, environment().fixture_checksum, observation().action_log
    )


def evidence(obs: Observation) -> ClickEvidence:
    return ClickEvidence(
        "art-shot-001",
        obs.observation_id,
        obs.attack_id,
        obs.environment_id,
        obs.source_sha,
        obs.fixture_checksum,
        3,
        "checkout-primary-action",
        "floating-help-button",
        "floating-help-button",
    )


def registry(*items: ClickEvidence) -> RegisteredOracleRegistry:
    return RegisteredOracleRegistry(
        plans=(plan(),),
        primary_targets={"cartwheel-fixture": "checkout-primary-action"},
        evidence=items,
    )


@pytest.mark.asyncio
async def test_browser_executes_only_recorded_steps_and_closes_idempotently() -> None:
    browser = FakeBrowserProvider((recording(),))
    session = await browser.open_session(environment())
    for index, step in enumerate(plan().steps):
        result = await browser.perform(session, index, step)
        assert result == observation().action_log[index]
    await browser.close_session(session)
    await browser.close_session(session)
    with pytest.raises(EnvironmentUnavailableError):
        await browser.perform(session, 0, plan().steps[0])


@pytest.mark.asyncio
async def test_browser_rejects_different_fixture_and_unrecorded_action() -> None:
    browser = FakeBrowserProvider((recording(),))
    with pytest.raises(EnvironmentUnavailableError):
        await browser.open_session(replace(environment(), fixture_checksum="f" * 64))
    session = await browser.open_session(environment())
    denied = await browser.perform(
        session, 0, ChatStep(agent_id="assistant", actor_id="synthetic-owner", message="refund")
    )
    assert denied.outcome == "blocked"
    assert denied.evidence_ids == ()
    changed = await browser.perform(session, 0, NavigateStep(path="/different"))
    assert changed.outcome == "blocked"
    await browser.close_session(session)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "https://outside.invalid/",
        "http://fake-preview.invalid/",
        "https://fake-preview.invalid@outside.invalid/",
    ],
)
async def test_off_origin_redirect_is_blocked_without_using_recorded_success(url: str) -> None:
    browser = FakeBrowserProvider((replace(recording(), redirects=(url, None, None, None, None)),))
    session = await browser.open_session(environment())
    result = await browser.perform(session, 0, plan().steps[0])
    assert result.outcome == "blocked"
    assert result.evidence_ids == ()
    await browser.close_session(session)


@pytest.mark.asyncio
async def test_worker_produces_golden_action_log_with_environment_binding() -> None:
    browser = FakeBrowserProvider((recording(),))
    result = await UIWorker(browser, registry()).run(plan(), environment())
    assert result.status == "completed"
    assert result.action_log == observation().action_log
    assert result.evidence_ids == ("art-dom-001", "art-shot-001", "art-shot-002")
    assert result.source_sha == environment().source_sha
    assert result.fixture_checksum == environment().fixture_checksum


@pytest.mark.asyncio
async def test_worker_rejects_unknown_oracle_before_browser_open() -> None:
    browser = FakeBrowserProvider(())
    bad = plan().model_copy(update={"oracle_ids": ("untrusted.model_assertion",)})
    with pytest.raises(UnknownOracleError):
        await UIWorker(browser, registry()).run(bad, environment())


class InterruptibleBrowser(FakeBrowserProvider):
    def __init__(self, *, failure: bool = False) -> None:
        super().__init__((recording(),))
        self.started = asyncio.Event()
        self.closed = False
        self.failure = failure

    async def perform(self, session_id: str, step_index: int, step: ActionStep) -> ActionRecord:
        self.started.set()
        if self.failure:
            raise EnvironmentUnavailableError("offline simulated connection loss")
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def close_session(self, session_id: str) -> None:
        self.closed = True
        await super().close_session(session_id)


@pytest.mark.asyncio
async def test_cancellation_closes_browser_and_propagates() -> None:
    browser = InterruptibleBrowser()
    task = asyncio.create_task(UIWorker(browser, registry()).run(plan(), environment()))
    await browser.started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert browser.closed


@pytest.mark.asyncio
async def test_timeout_closes_browser_and_reports_budget_exceeded() -> None:
    browser = InterruptibleBrowser()
    spec = plan().model_copy(update={"max_runtime_seconds": 1})
    result = await UIWorker(browser, registry()).run(spec, environment())
    assert result.status == "budget_exceeded"
    assert browser.closed


@pytest.mark.asyncio
async def test_environment_failure_is_not_a_successful_observation() -> None:
    browser = InterruptibleBrowser(failure=True)
    result = await UIWorker(browser, registry()).run(plan(), environment())
    assert result.status == "environment_error"
    assert browser.closed
    assert registry().evaluate("ui.primary_action_reachable", result).outcome == "inconclusive"


def test_oracle_needs_structured_bound_click_evidence_not_blocked_text() -> None:
    obs = observation()
    assert registry().evaluate("ui.primary_action_reachable", obs).outcome == "inconclusive"
    oracle = registry(evidence(obs))
    verdict = oracle.evaluate("ui.primary_action_reachable", obs)
    assert verdict.outcome == "fail"
    assert verdict.oracle_kind == "hard"
    assert verdict.evidence_ids == ("art-shot-001",)
    forged = obs.model_copy(update={"environment_id": "another-environment"})
    assert oracle.evaluate("ui.primary_action_reachable", forged).outcome == "inconclusive"
    with pytest.raises(UnknownOracleError):
        oracle.evaluate("unknown.oracle", obs)


def test_oracle_accepts_actual_primary_action_and_rejects_contradictory_records() -> None:
    obs = observation()
    click = obs.action_log[3].model_copy(update={"outcome": "ok"})
    obs = obs.model_copy(update={"action_log": (*obs.action_log[:3], click, obs.action_log[4])})
    proof = replace(
        evidence(obs),
        hit_target="checkout-primary-action",
        received_target="checkout-primary-action",
    )
    assert registry(proof).evaluate("ui.primary_action_reachable", obs).outcome == "pass"
    contradictory = replace(proof, received_target=None)
    assert (
        registry(contradictory).evaluate("ui.primary_action_reachable", obs).outcome
        == "inconclusive"
    )


@pytest.mark.asyncio
async def test_sandbox_lifecycle_and_fixture_isolation() -> None:
    fixture = Fixture("baseline-v1", "a" * 64, frozenset({"aaaaaaaa"}))
    sandbox = FakeSandboxProvider({"cartwheel-fixture": fixture})
    first = await sandbox.create(
        target_id="cartwheel-fixture",
        source_sha="aaaaaaaa",
        fixture_id="baseline-v1",
        mode="gate_compare",
    )
    second = await sandbox.create(
        target_id="cartwheel-fixture",
        source_sha="aaaaaaaa",
        fixture_id="baseline-v1",
        mode="gate_compare",
    )
    assert first.environment_id != second.environment_id
    assert await sandbox.verify_fixture(first.environment_id, "a" * 64)
    assert not await sandbox.verify_fixture(first.environment_id, "b" * 64)
    await sandbox.destroy(first.environment_id)
    await sandbox.destroy(first.environment_id)
    assert not await sandbox.verify_fixture(first.environment_id, "a" * 64)
    assert await sandbox.verify_fixture(second.environment_id, "a" * 64)
    await sandbox.destroy(second.environment_id)
