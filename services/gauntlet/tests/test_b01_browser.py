"""B-01c4: Anchor session lifecycle around the scoped Playwright port."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_b01_local_browser import ENVIRONMENT, SUBJECT, FakeBrowser, FakeRoute

from gauntlet.contracts import CaptureStep, NavigateStep, ResizeStep
from gauntlet.integrations.anchor.provider import AnchorBrowserProvider
from gauntlet.integrations.anchor.sdk import SdkAnchorRuntime
from gauntlet.integrations.browser_evidence import BrowserEvidenceCollector
from gauntlet.integrations.local_artifacts import LocalArtifactStore
from gauntlet.ports.errors import EnvironmentUnavailableError
from gauntlet.ports.sandbox import EnvironmentHandle


class FakeConnection:
    def __init__(self) -> None:
        self.browser = FakeBrowser()
        self.closed = False
        self.fail_close = False

    async def close(self) -> None:
        if self.fail_close:
            self.fail_close = False
            raise RuntimeError("close failed")
        self.closed = True


class FakeRuntime:
    def __init__(self) -> None:
        self.connections: list[FakeConnection] = []

    async def open(self) -> FakeConnection:
        connection = FakeConnection()
        self.connections.append(connection)
        return connection


class FailingContextBrowser(FakeBrowser):
    async def new_context(self, **options: object) -> None:
        raise RuntimeError("context failed")


class FailingContextRuntime(FakeRuntime):
    async def open(self) -> FakeConnection:
        connection = await super().open()
        connection.browser = FailingContextBrowser()
        connection.fail_close = True
        return connection


def preview(origin: str = "https://scope-123.proxy.daytona.work") -> EnvironmentHandle:
    return EnvironmentHandle(**{**vars(ENVIRONMENT), "preview_origin": origin})


def provider(tmp_path: Path, runtime: FakeRuntime) -> AnchorBrowserProvider:
    return AnchorBrowserProvider(
        runtime,
        BrowserEvidenceCollector(LocalArtifactStore(tmp_path)),
        preview_domain_suffix=".proxy.daytona.work",
    )


def test_rejects_wrong_identity_and_preview_before_cloud_open(tmp_path: Path) -> None:
    async def scenario() -> None:
        runtime = FakeRuntime()
        adapter = provider(tmp_path, runtime)
        with pytest.raises(EnvironmentUnavailableError):
            await adapter.open_session(
                preview(), SUBJECT.model_copy(update={"source_sha": "c" * 40})
            )
        for origin in (
            "http://scope-123.proxy.daytona.work",
            "https://scope-123.proxy.daytona.work.evil",
            "https://scope-123.proxy.daytona.work/path",
            "https://user@scope-123.proxy.daytona.work",
            "https://scope-123.proxy.daytona.work:443",
            "https://scope-123.proxy.daytona.work:bad",
        ):
            with pytest.raises(EnvironmentUnavailableError):
                await adapter.open_session(preview(origin), SUBJECT)
        assert runtime.connections == []

    asyncio.run(scenario())


def test_typed_steps_capture_and_scope_guard(tmp_path: Path) -> None:
    async def scenario() -> None:
        runtime = FakeRuntime()
        adapter = provider(tmp_path, runtime)
        session = await adapter.open_session(preview(), SUBJECT)
        connection = runtime.connections[0]
        context = connection.browser.contexts[0]
        assert (await adapter.perform(session, 0, NavigateStep(path="/checkout"))).outcome == "ok"
        assert context.page.url == "https://scope-123.proxy.daytona.work/checkout"
        assert (
            await adapter.perform(session, 1, ResizeStep(width=375, height=812))
        ).outcome == "ok"
        assert context.page.viewport == {"width": 375, "height": 812}
        capture = await adapter.perform(session, 2, CaptureStep())
        assert capture.outcome == "ok" and len(capture.evidence_ids) == 1
        off_origin = FakeRoute("https://other.example/collect")
        assert context.handler is not None
        await context.handler(off_origin)
        assert off_origin.result == "abort"
        assert (
            await adapter.perform(session, 3, ResizeStep(width=375, height=812))
        ).outcome == "blocked"
        await adapter.close_session(session)
        await adapter.close_session(session)
        assert context.closed and connection.closed

    asyncio.run(scenario())


def test_failed_close_can_be_retried_without_losing_session(tmp_path: Path) -> None:
    async def scenario() -> None:
        runtime = FakeRuntime()
        adapter = provider(tmp_path, runtime)
        session = await adapter.open_session(preview(), SUBJECT)
        connection = runtime.connections[0]
        connection.fail_close = True
        with pytest.raises(EnvironmentUnavailableError):
            await adapter.close_session(session)
        assert session in adapter.pending_cleanup_ids
        await adapter.close_session(session)
        assert adapter.pending_cleanup_ids == ()
        assert connection.closed

    asyncio.run(scenario())


def test_partial_open_failed_close_remains_retriable(tmp_path: Path) -> None:
    async def scenario() -> None:
        runtime = FailingContextRuntime()
        adapter = provider(tmp_path, runtime)
        with pytest.raises(EnvironmentUnavailableError):
            await adapter.open_session(preview(), SUBJECT)
        assert len(adapter.pending_cleanup_ids) == 1
        await adapter.retry_pending_cleanup()
        assert adapter.pending_cleanup_ids == ()
        assert runtime.connections[0].closed

    asyncio.run(scenario())


def test_runtime_timeout_is_environment_error_and_cancellation_propagates(tmp_path: Path) -> None:
    class TimeoutRuntime:
        async def open(self) -> None:
            raise TimeoutError("Anchor timed out")

    class CancelRuntime:
        async def open(self) -> None:
            raise asyncio.CancelledError()

    async def scenario() -> None:
        timed = AnchorBrowserProvider(
            TimeoutRuntime(),
            BrowserEvidenceCollector(LocalArtifactStore(tmp_path)),
            preview_domain_suffix=".proxy.daytona.work",
        )
        with pytest.raises(EnvironmentUnavailableError):
            await timed.open_session(preview(), SUBJECT)
        cancelled = AnchorBrowserProvider(
            CancelRuntime(),
            BrowserEvidenceCollector(LocalArtifactStore(tmp_path)),
            preview_domain_suffix=".proxy.daytona.work",
        )
        with pytest.raises(asyncio.CancelledError):
            await cancelled.open_session(preview(), SUBJECT)

    asyncio.run(scenario())


class FakeAnchorConnect:
    def __init__(self, browser: FakeBrowser) -> None:
        self.browser = browser
        self.exited = False

    async def __aenter__(self) -> FakeBrowser:
        return self.browser

    async def __aexit__(self, *_args: object) -> None:
        self.exited = True


class FakeAnchorClient:
    def __init__(self) -> None:
        self.config: dict[str, object] | None = None
        self.deleted: list[str] = []
        self.browser_instance = FakeBrowser()
        self.connection = FakeAnchorConnect(self.browser_instance)
        self.fail_connect = False
        self.fail_delete = False
        self.sessions = self
        self.browser = self

    async def create_session(self, **kwargs: object) -> SimpleNamespace:
        self.config = kwargs
        return SimpleNamespace(data=SimpleNamespace(id="anchor-session-123"))

    async def connect(self, session_id: str) -> FakeAnchorConnect:
        assert session_id == "anchor-session-123"
        if self.fail_connect:
            raise TimeoutError("CDP timed out")
        return self.connection

    async def delete_session(self, session_id: str, *, timeout: float) -> None:
        assert timeout == 15
        if self.fail_delete:
            self.fail_delete = False
            raise RuntimeError("delete failed")
        self.deleted.append(session_id)


def test_sdk_requires_live_flag_and_uses_custom_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        client = FakeAnchorClient()
        runtime = SdkAnchorRuntime(
            client,
            proxy_server="http://egress-proxy.internal:8080",
            proxy_username="operator",
            proxy_password="synthetic-secret",
        )
        monkeypatch.delenv("RUN_LIVE_INTEGRATIONS", raising=False)
        with pytest.raises(EnvironmentUnavailableError):
            await runtime.open()
        assert client.config is None
        monkeypatch.setenv("RUN_LIVE_INTEGRATIONS", "1")
        connection = await runtime.open()
        assert connection.browser is client.browser_instance
        assert client.config is not None
        assert client.config["session"] == {
            "recording": {"active": True},
            "proxy": {
                "type": "custom",
                "server": "http://egress-proxy.internal:8080",
                "username": "operator",
                "password": "synthetic-secret",
                "active": True,
            },
        }
        await connection.close()
        await connection.close()
        assert client.connection.exited
        assert client.deleted == ["anchor-session-123"]

    asyncio.run(scenario())


def test_sdk_retains_failed_connect_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        monkeypatch.setenv("RUN_LIVE_INTEGRATIONS", "1")
        client = FakeAnchorClient()
        client.fail_connect = True
        client.fail_delete = True
        runtime = SdkAnchorRuntime(
            client,
            proxy_server="http://egress-proxy.internal:8080",
            proxy_username="operator",
            proxy_password="synthetic-secret",
        )
        with pytest.raises(EnvironmentUnavailableError):
            await runtime.open()
        assert runtime.pending_cleanup_ids == ("anchor-session-123",)
        await runtime.retry_pending_cleanup()
        assert runtime.pending_cleanup_ids == ()
        assert client.deleted == ["anchor-session-123"]

    asyncio.run(scenario())
