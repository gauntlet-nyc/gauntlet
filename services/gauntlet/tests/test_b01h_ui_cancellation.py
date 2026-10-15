"""A cancelled UI attempt still releases its browser session."""

import asyncio
from pathlib import Path

import pytest

from gauntlet.contracts import ActionRecord, AttackSpec, EvidenceSubject
from gauntlet.contracts.gate import ActionStep
from gauntlet.ports.errors import EnvironmentUnavailableError
from gauntlet.ports.sandbox import EnvironmentHandle
from gauntlet.verification.registry import RegisteredOracleRegistry
from gauntlet.workers.ui import UIWorker

GOLDEN = Path(__file__).resolve().parents[3] / "docs/contracts/examples/ui-plan.v1.json"


def setup() -> tuple[AttackSpec, EnvironmentHandle, EvidenceSubject, RegisteredOracleRegistry]:
    spec = AttackSpec.model_validate_json(GOLDEN.read_text())
    environment = EnvironmentHandle(
        "env-ui-cancel",
        spec.target_id,
        "a" * 40,
        spec.fixture_id,
        "b" * 64,
        "https://fake-preview.invalid",
    )
    subject = EvidenceSubject(
        run_id="run-ui-cancel",
        attempt_id="attempt-ui-cancel",
        observation_id="obs-ui-cancel",
        environment_id=environment.environment_id,
        source_sha=environment.source_sha,
        fixture_checksum=environment.fixture_checksum,
        collector="browser_collector",
    )
    registry = RegisteredOracleRegistry(plans=(spec,), primary_targets={}, evidence=())
    return spec, environment, subject, registry


class SlowCloseBrowser:
    def __init__(self, *, fail_close: bool = False) -> None:
        self.perform_started = asyncio.Event()
        self.close_started = asyncio.Event()
        self.release_close = asyncio.Event()
        self.closed = False
        self.fail_close = fail_close

    async def open_session(self, environment: EnvironmentHandle, subject: EvidenceSubject) -> str:
        return "session-ui-cancel"

    async def perform(self, session_id: str, step_index: int, step: ActionStep) -> ActionRecord:
        self.perform_started.set()
        await asyncio.Event().wait()
        raise AssertionError("perform was not interrupted")

    async def close_session(self, session_id: str) -> None:
        self.close_started.set()
        await self.release_close.wait()
        if self.fail_close:
            raise EnvironmentUnavailableError("private provider detail")
        self.closed = True


def test_repeated_cancellation_finishes_browser_cleanup() -> None:
    async def scenario() -> None:
        spec, environment, subject, registry = setup()
        browser = SlowCloseBrowser()
        task = asyncio.create_task(UIWorker(browser, registry).run(spec, environment, subject))
        await asyncio.wait_for(browser.perform_started.wait(), 1)
        task.cancel()
        await asyncio.wait_for(browser.close_started.wait(), 1)
        task.cancel()
        browser.release_close.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        assert browser.closed

    asyncio.run(scenario())


def test_failed_cleanup_during_cancellation_is_logged_without_provider_detail(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def scenario() -> None:
        spec, environment, subject, registry = setup()
        browser = SlowCloseBrowser(fail_close=True)
        task = asyncio.create_task(UIWorker(browser, registry).run(spec, environment, subject))
        await asyncio.wait_for(browser.perform_started.wait(), 1)
        task.cancel()
        await asyncio.wait_for(browser.close_started.wait(), 1)
        browser.release_close.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)

    asyncio.run(scenario())
    assert "UI browser session cleanup failed" in caplog.text
    assert "attempt=attempt-ui-cancel environment=env-ui-cancel" in caplog.text
    assert "private provider detail" not in caplog.text


def test_timed_out_cleanup_during_cancellation_is_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def scenario() -> None:
        spec, environment, subject, registry = setup()
        browser = SlowCloseBrowser()
        spec = spec.model_copy(update={"max_runtime_seconds": 1})
        task = asyncio.create_task(UIWorker(browser, registry).run(spec, environment, subject))
        await asyncio.wait_for(browser.perform_started.wait(), 1)
        task.cancel()
        await asyncio.wait_for(browser.close_started.wait(), 1)
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
        assert not browser.closed

    asyncio.run(scenario())
    assert "UI browser session cleanup failed (timeout)" in caplog.text
