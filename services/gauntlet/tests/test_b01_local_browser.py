"""Local browser port: exact session identity, typed steps and origin boundary."""

import asyncio
from pathlib import Path

import pytest

from gauntlet.contracts import (
    CaptureStep,
    EvidenceSubject,
    NavigateStep,
    PressStep,
    ResizeStep,
    TypeStep,
)
from gauntlet.integrations.browser_evidence import BrowserEvidenceCollector
from gauntlet.integrations.local_artifacts import LocalArtifactStore
from gauntlet.integrations.local_browser import LocalBrowserProvider
from gauntlet.ports.errors import EnvironmentUnavailableError
from gauntlet.ports.sandbox import EnvironmentHandle


class FakeLocator:
    def __init__(self) -> None:
        self.values: list[str] = []

    async def fill(self, value: str) -> None:
        self.values.append(value)


class FakeKeyboard:
    def __init__(self) -> None:
        self.keys: list[str] = []

    async def press(self, key: str) -> None:
        self.keys.append(key)


class FakeMouse:
    async def wheel(self, x: int, y: int) -> None:
        pass


class FakePage:
    def __init__(self) -> None:
        self.url = "about:blank"
        self.viewport: dict[str, int] | None = None
        self.keyboard = FakeKeyboard()
        self.mouse = FakeMouse()
        self.locator = FakeLocator()
        self.redirect: str | None = None
        self.closed = False

    async def goto(self, url: str, *, wait_until: str) -> None:
        assert wait_until == "domcontentloaded"
        self.url = self.redirect or url

    async def set_viewport_size(self, size: dict[str, int]) -> None:
        self.viewport = size

    def get_by_test_id(self, target: str) -> FakeLocator:
        assert target == "customer-email"
        return self.locator

    async def screenshot(self) -> bytes:
        return b"\x89PNG\r\n\x1a\nlocal-browser"

    async def close(self) -> None:
        self.closed = True


class FakeRoute:
    def __init__(self, url: str, status: int = 200) -> None:
        self.request = type("Request", (), {"url": url})()
        self.result: str | None = None
        self.response = type("Response", (), {"status": status})()

    async def fetch(self, *, max_redirects: int) -> object:
        assert max_redirects == 0
        return self.response

    async def fulfill(self, *, response: object) -> None:
        assert response is self.response
        self.result = "fulfill"

    async def abort(self) -> None:
        self.result = "abort"


class FakeContext:
    def __init__(self) -> None:
        self.page = FakePage()
        self.handler = None
        self.closed = False
        self.fail_close = False
        self.pages = [self.page]
        self.events: dict[str, object] = {}

    async def route(self, pattern: str, handler: object) -> None:
        assert pattern == "**/*"
        self.handler = handler

    async def new_page(self) -> FakePage:
        return self.page

    def on(self, event: str, handler: object) -> None:
        self.events[event] = handler

    async def close(self) -> None:
        self.closed = True
        if self.fail_close:
            self.fail_close = False
            raise RuntimeError("simulated close failure")


class FakeBrowser:
    def __init__(self) -> None:
        self.contexts: list[FakeContext] = []
        self.options: dict[str, object] | None = None

    async def new_context(self, **options: object) -> FakeContext:
        self.options = options
        context = FakeContext()
        self.contexts.append(context)
        return context


SUBJECT = EvidenceSubject(
    run_id="run-local-1",
    attempt_id="attempt-local-1",
    observation_id="obs-local-1",
    environment_id="env-local-1",
    source_sha="a" * 40,
    fixture_checksum="b" * 64,
    collector="browser_collector",
)
ENVIRONMENT = EnvironmentHandle(
    environment_id=SUBJECT.environment_id,
    target_id="cartwheel",
    source_sha=SUBJECT.source_sha,
    fixture_id="fixture-cartwheel",
    fixture_checksum=SUBJECT.fixture_checksum,
    preview_origin="http://127.0.0.1:3100",
)


def provider(tmp_path: Path, browser: FakeBrowser) -> LocalBrowserProvider:
    return LocalBrowserProvider(browser, BrowserEvidenceCollector(LocalArtifactStore(tmp_path)))


def test_open_rejects_mismatched_subject_and_malformed_origins(tmp_path: Path) -> None:
    async def scenario() -> None:
        browser = FakeBrowser()
        adapter = provider(tmp_path, browser)
        with pytest.raises(EnvironmentUnavailableError):
            await adapter.open_session(
                ENVIRONMENT, SUBJECT.model_copy(update={"source_sha": "c" * 40})
            )
        for origin in (
            "https://example.com:3100",
            "http://127.0.0.1.evil:3100",
            "http://127.0.0.1:3100/path",
            "http://user@127.0.0.1:3100",
            "http://127.0.0.1:bad",
        ):
            with pytest.raises(EnvironmentUnavailableError):
                await adapter.open_session(
                    EnvironmentHandle(**{**vars(ENVIRONMENT), "preview_origin": origin}), SUBJECT
                )
        assert browser.contexts == []

    asyncio.run(scenario())


def test_typed_steps_and_artifact_are_bound_to_session(tmp_path: Path) -> None:
    async def scenario() -> None:
        browser = FakeBrowser()
        adapter = provider(tmp_path, browser)
        session = await adapter.open_session(ENVIRONMENT, SUBJECT)
        context = browser.contexts[0]
        assert browser.options == {
            "viewport": {"width": 1280, "height": 720},
            "service_workers": "block",
            "accept_downloads": False,
        }
        assert (await adapter.perform(session, 0, NavigateStep(path="/checkout"))).outcome == "ok"
        assert context.page.url == "http://127.0.0.1:3100/checkout"
        assert (
            await adapter.perform(session, 1, ResizeStep(width=375, height=812))
        ).outcome == "ok"
        assert context.page.viewport == {"width": 375, "height": 812}
        assert (
            await adapter.perform(session, 2, TypeStep(target="customer-email", value="a@b.test"))
        ).outcome == "ok"
        assert context.page.locator.values == ["a@b.test"]
        captured = await adapter.perform(session, 3, CaptureStep())
        assert captured.outcome == "ok" and len(captured.evidence_ids) == 1
        await adapter.close_session(session)
        await adapter.close_session(session)
        assert context.closed

    asyncio.run(scenario())


def test_route_aborts_egress_and_redirect_is_blocked(tmp_path: Path) -> None:
    async def scenario() -> None:
        browser = FakeBrowser()
        adapter = provider(tmp_path, browser)
        session = await adapter.open_session(ENVIRONMENT, SUBJECT)
        context = browser.contexts[0]
        assert context.handler is not None
        allowed = FakeRoute("http://127.0.0.1:3100/_next/app.js")
        denied = FakeRoute("http://127.0.0.1.evil:3100/steal")
        redirect = FakeRoute("http://127.0.0.1:3100/redirect", status=302)
        await context.handler(allowed)
        await context.handler(denied)
        await context.handler(redirect)
        assert allowed.result == "fulfill"
        assert denied.result == "abort"
        assert redirect.result == "abort"
        context.page.redirect = "http://evil.test/landing"
        record = await adapter.perform(session, 0, NavigateStep(path="/checkout"))
        assert record.outcome == "blocked"
        await adapter.close_session(session)

    asyncio.run(scenario())


def test_sequence_and_failed_close(tmp_path: Path) -> None:
    async def scenario() -> None:
        browser = FakeBrowser()
        adapter = provider(tmp_path, browser)
        session = await adapter.open_session(ENVIRONMENT, SUBJECT)
        with pytest.raises(EnvironmentUnavailableError):
            await adapter.perform(session, 1, NavigateStep(path="/checkout"))
        browser.contexts[0].fail_close = True
        with pytest.raises(EnvironmentUnavailableError):
            await adapter.close_session(session)
        await adapter.close_session(session)

    asyncio.run(scenario())


def test_popup_and_shortcut_are_blocked(tmp_path: Path) -> None:
    async def scenario() -> None:
        browser = FakeBrowser()
        adapter = provider(tmp_path, browser)
        session = await adapter.open_session(ENVIRONMENT, SUBJECT)
        context = browser.contexts[0]
        await adapter.perform(session, 0, NavigateStep(path="/checkout"))
        popup = FakePage()
        context.events["page"](popup)
        await asyncio.sleep(0)
        assert popup.closed
        assert (
            await adapter.perform(session, 1, ResizeStep(width=375, height=812))
        ).outcome == "blocked"
        await adapter.close_session(session)
        session = await adapter.open_session(ENVIRONMENT, SUBJECT)
        await adapter.perform(session, 0, NavigateStep(path="/checkout"))
        blocked_key = await adapter.perform(session, 1, PressStep(key="Control+L"))
        assert blocked_key.outcome == "blocked"
        assert browser.contexts[1].page.keyboard.keys == []
        await adapter.close_session(session)

    asyncio.run(scenario())


def test_blocked_step_advances_sequence(tmp_path: Path) -> None:
    async def scenario() -> None:
        browser = FakeBrowser()
        adapter = provider(tmp_path, browser)
        session = await adapter.open_session(ENVIRONMENT, SUBJECT)
        await adapter.perform(session, 0, NavigateStep(path="/checkout"))
        blocked = await adapter.perform(session, 1, PressStep(key="Control+L"))
        assert blocked.outcome == "blocked"
        # The next index is accepted; a stale index is a sequence error.
        assert (await adapter.perform(session, 2, PressStep(key="Tab"))).outcome == "ok"
        with pytest.raises(EnvironmentUnavailableError):
            await adapter.perform(session, 2, PressStep(key="Tab"))
        await adapter.close_session(session)

    asyncio.run(scenario())


def test_loopback_rule_matches_fixture_identity(tmp_path: Path) -> None:
    async def scenario() -> None:
        browser = FakeBrowser()
        adapter = provider(tmp_path, browser)
        with pytest.raises(EnvironmentUnavailableError):
            await adapter.open_session(
                EnvironmentHandle(**{**vars(ENVIRONMENT), "preview_origin": "http://localhost:3100"}),
                SUBJECT,
            )
        session = await adapter.open_session(
            EnvironmentHandle(**{**vars(ENVIRONMENT), "preview_origin": "http://[::1]:3100"}),
            SUBJECT,
        )
        await adapter.close_session(session)

    asyncio.run(scenario())
