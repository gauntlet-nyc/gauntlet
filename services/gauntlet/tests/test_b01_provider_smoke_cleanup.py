"""Final live-smoke cleanup survives cancellation and records failures."""

import asyncio

from gauntlet.execution.provider_smoke_cleanup import finish_smoke_resources


class Browser:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.retried = False

    @property
    def pending_cleanup_ids(self) -> tuple[str, ...]:
        return ()

    async def retry_pending_cleanup(self) -> None:
        self.started.set()
        await self.release.wait()
        self.retried = True


class Sandbox:
    def __init__(self) -> None:
        self.pending_cleanup_ids = ("sandbox-1",)
        self.destroyed: list[str] = []

    async def destroy(self, environment_id: str) -> None:
        self.destroyed.append(environment_id)
        self.pending_cleanup_ids = ()


class Anchor:
    def __init__(self, *, fail_retry: bool = False) -> None:
        self.pending_cleanup_ids = ("session-1",)
        self.fail_retry = fail_retry
        self.closed = False

    async def retry_pending_cleanup(self) -> None:
        if self.fail_retry:
            raise RuntimeError("sensitive provider detail")
        self.pending_cleanup_ids = ()

    async def close(self) -> None:
        self.closed = True


class Daytona:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def test_repeated_cancellation_finishes_every_cleanup_step() -> None:
    async def scenario() -> None:
        browser, sandbox, anchor, daytona = Browser(), Sandbox(), Anchor(), Daytona()
        task = asyncio.create_task(finish_smoke_resources(browser, sandbox, anchor, daytona))
        await asyncio.wait_for(browser.started.wait(), 1)
        task.cancel()
        task.cancel()
        browser.release.set()
        result = await asyncio.wait_for(task, 1)
        assert result.cancelled
        assert result.errors == ()
        assert browser.retried
        assert sandbox.destroyed == ["sandbox-1"]
        assert anchor.closed and daytona.closed

    asyncio.run(scenario())


def test_cleanup_error_is_sanitized_and_does_not_skip_other_resources() -> None:
    async def scenario() -> None:
        browser, sandbox, anchor, daytona = Browser(), Sandbox(), Anchor(fail_retry=True), Daytona()
        browser.release.set()
        result = await finish_smoke_resources(browser, sandbox, anchor, daytona)
        assert result.errors == ("anchor_session_cleanup",)
        assert "sensitive" not in repr(result)
        assert browser.retried and sandbox.destroyed == ["sandbox-1"]
        assert anchor.closed and daytona.closed

    asyncio.run(scenario())
