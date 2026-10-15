"""A cancelled partial Anchor open must finish or retain paid-session cleanup."""

import asyncio
from pathlib import Path

import pytest
from test_b01_local_browser import ENVIRONMENT, SUBJECT, FakeBrowser

from gauntlet.integrations.anchor.provider import AnchorBrowserProvider
from gauntlet.integrations.browser_evidence import BrowserEvidenceCollector
from gauntlet.integrations.local_artifacts import LocalArtifactStore
from gauntlet.ports.sandbox import EnvironmentHandle


class BlockingBrowser(FakeBrowser):
    def __init__(self) -> None:
        super().__init__()
        self.open_started = asyncio.Event()

    async def new_context(self, **options: object) -> None:
        self.open_started.set()
        await asyncio.Event().wait()


class PausedConnection:
    def __init__(self, *, fail_close: bool = False) -> None:
        self.browser = BlockingBrowser()
        self.close_started = asyncio.Event()
        self.close_cancelled = asyncio.Event()
        self.release_close = asyncio.Event()
        self.closed = False
        self.fail_close = fail_close

    async def close(self) -> None:
        self.close_started.set()
        try:
            await self.release_close.wait()
        except asyncio.CancelledError:
            self.close_cancelled.set()
            raise
        if self.fail_close:
            self.fail_close = False
            raise RuntimeError("synthetic close failure")
        self.closed = True


class Runtime:
    def __init__(self, connection: PausedConnection) -> None:
        self.connection = connection

    async def open(self) -> PausedConnection:
        return self.connection


def adapter(
    tmp_path: Path,
    connection: PausedConnection,
    *,
    cleanup_timeout_seconds: float | None = None,
) -> AnchorBrowserProvider:
    runtime = Runtime(connection)
    collector = BrowserEvidenceCollector(LocalArtifactStore(tmp_path))
    if cleanup_timeout_seconds is None:
        return AnchorBrowserProvider(
            runtime, collector, preview_domain_suffix=".proxy.daytona.work"
        )
    return AnchorBrowserProvider(
        runtime,
        collector,
        preview_domain_suffix=".proxy.daytona.work",
        cleanup_timeout_seconds=cleanup_timeout_seconds,
    )


def preview() -> EnvironmentHandle:
    return EnvironmentHandle(
        **{**vars(ENVIRONMENT), "preview_origin": "https://scope-123.proxy.daytona.work"}
    )


@pytest.mark.parametrize("fail_close", [False, True])
def test_repeated_cancellation_finishes_or_tracks_partial_open_cleanup(
    tmp_path: Path, fail_close: bool
) -> None:
    async def scenario() -> None:
        connection = PausedConnection(fail_close=fail_close)
        provider = adapter(tmp_path, connection)
        opening = asyncio.create_task(provider.open_session(preview(), SUBJECT))
        await asyncio.wait_for(connection.browser.open_started.wait(), 1)
        opening.cancel()
        await asyncio.wait_for(connection.close_started.wait(), 1)

        try:
            opening.cancel()
            await asyncio.sleep(0)
            assert not opening.done(), "cleanup must survive a second cancellation"
        finally:
            connection.release_close.set()

        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(opening, 1)

        if fail_close:
            assert not connection.closed
            assert len(provider.pending_cleanup_ids) == 1
            await provider.retry_pending_cleanup()
            assert connection.closed
        else:
            assert connection.closed
        assert provider.pending_cleanup_ids == ()

    asyncio.run(scenario())


def test_hung_close_times_out_and_remains_retriable(tmp_path: Path) -> None:
    async def scenario() -> None:
        connection = PausedConnection()
        provider = adapter(tmp_path, connection, cleanup_timeout_seconds=0.02)
        opening = asyncio.create_task(provider.open_session(preview(), SUBJECT))
        await asyncio.wait_for(connection.browser.open_started.wait(), 1)
        opening.cancel()
        await asyncio.wait_for(connection.close_started.wait(), 1)

        try:
            done, _ = await asyncio.wait({opening}, timeout=0.5)
            assert opening in done, "hung cleanup must not hold the cancelled caller"
        finally:
            connection.release_close.set()

        with pytest.raises(asyncio.CancelledError):
            await opening
        await asyncio.wait_for(connection.close_cancelled.wait(), 1)
        assert not connection.closed
        assert len(provider.pending_cleanup_ids) == 1

        await provider.retry_pending_cleanup()
        assert connection.closed
        assert provider.pending_cleanup_ids == ()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "timeout",
    [0, -1, float("nan"), float("inf"), float("-inf"), True, "1", 10**1000],
)
def test_cleanup_timeout_must_be_finite_and_positive(tmp_path: Path, timeout: object) -> None:
    with pytest.raises(ValueError, match="cleanup timeout must be finite and positive"):
        adapter(tmp_path, PausedConnection(), cleanup_timeout_seconds=timeout)
