"""Local browser port: exact session identity, typed steps and origin boundary."""

import asyncio
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest
from image_samples import PNG

from gauntlet.contracts import (
    CaptureStep,
    ClickStep,
    EvidenceSubject,
    InspectStep,
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

    async def wait_for_load_state(self, state: str) -> None:
        assert state == "networkidle"

    async def set_viewport_size(self, size: dict[str, int]) -> None:
        self.viewport = size

    def get_by_test_id(self, target: str) -> FakeLocator:
        assert target == "customer-email"
        return self.locator

    async def screenshot(self, *, type: str = "png") -> bytes:
        return PNG

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
                EnvironmentHandle(
                    **{**vars(ENVIRONMENT), "preview_origin": "http://localhost:3100"}
                ),
                SUBJECT,
            )
        session = await adapter.open_session(
            EnvironmentHandle(**{**vars(ENVIRONMENT), "preview_origin": "http://[::1]:3100"}),
            SUBJECT,
        )
        await adapter.close_session(session)

    asyncio.run(scenario())


@pytest.mark.skipif(
    not Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome").exists(),
    reason="local Chrome is needed for browser hydration evidence",
)
def test_click_waits_for_client_handler_after_navigation(tmp_path: Path) -> None:
    """A DOM-ready button must receive its late client handler before a typed click."""
    async_playwright = pytest.importorskip("playwright.async_api").async_playwright
    html = b"""<button data-testid="checkout-primary-action">Place order</button>
    <script async src="/hydrate.js"></script>"""
    script = b"""document.querySelector('[data-testid="checkout-primary-action"]')
      .addEventListener('click', async () => {
        const response = await fetch('/api/orders', {method: 'POST'});
        if (response.status === 201) {
          const receipt = document.createElement('p');
          receipt.dataset.testid = 'order-receipt';
          receipt.textContent = 'Order placed';
          document.body.appendChild(receipt);
        }
      });"""

    class Handler(BaseHTTPRequestHandler):
        order_posts = 0

        def do_GET(self) -> None:
            if self.path == "/hydrate.js":
                time.sleep(0.35)
                body, media_type = script, "application/javascript"
            else:
                body, media_type = html, "text/html"
            self.send_response(200)
            self.send_header("Content-Type", media_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            if self.path == "/api/orders":
                Handler.order_posts += 1
                self.send_response(201)
                self.send_header("Content-Length", "0")
                self.end_headers()

        def log_message(self, _format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    async def scenario() -> None:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                headless=True,
            )
            try:
                origin = f"http://127.0.0.1:{server.server_port}"
                adapter = provider(
                    tmp_path,
                    browser,
                )
                environment = EnvironmentHandle(**{**vars(ENVIRONMENT), "preview_origin": origin})
                session = await adapter.open_session(environment, SUBJECT)
                try:
                    navigated = await adapter.perform(session, 0, NavigateStep(path="/checkout"))
                    assert navigated.outcome == "ok"
                    assert (
                        await adapter.perform(
                            session, 1, ClickStep(target="checkout-primary-action")
                        )
                    ).outcome == "ok"
                    receipt = await adapter.perform(session, 2, InspectStep(target="order-receipt"))
                    assert receipt.outcome == "ok"
                    assert Handler.order_posts == 1
                finally:
                    await adapter.close_session(session)
            finally:
                await browser.close()

    try:
        asyncio.run(scenario())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
