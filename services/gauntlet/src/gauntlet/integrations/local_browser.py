"""Loopback-only Playwright adapter for synthetic browser diagnostics.

The caller supplies an already launched browser. This adapter never imports a
provider SDK, accepts planner JavaScript or expands its preview origin.
Browser routing is a local guard, not DNS/network isolation for a cloud run.
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit
from uuid import uuid4

from gauntlet.contracts import (
    ActionRecord,
    ActionStep,
    CaptureStep,
    ClickStep,
    EvidenceSubject,
    InspectStep,
    NavigateStep,
    PressStep,
    ResizeStep,
    ScrollStep,
    TypeStep,
)
from gauntlet.ports.browser import is_browser_subject_for
from gauntlet.ports.errors import EnvironmentUnavailableError
from gauntlet.ports.sandbox import EnvironmentHandle

from .browser_evidence import BrowserEvidenceCollector, BrowserPage

_PRESS_KEYS = frozenset(
    {
        "Enter",
        "Tab",
        "Escape",
        "Space",
        "Backspace",
        "Delete",
        "ArrowUp",
        "ArrowDown",
        "ArrowLeft",
        "ArrowRight",
        "Home",
        "End",
        "PageUp",
        "PageDown",
    }
)


class _RouteRequest(Protocol):
    url: str


class _Route(Protocol):
    request: _RouteRequest

    async def fetch(self, *, max_redirects: int) -> "_RouteResponse": ...

    async def fulfill(self, *, response: "_RouteResponse") -> None: ...

    async def abort(self) -> None: ...


class _RouteResponse(Protocol):
    status: int


class _Mouse(Protocol):
    async def click(self, x: float, y: float) -> None: ...

    async def wheel(self, x: int, y: int) -> None: ...


class _Keyboard(Protocol):
    async def press(self, key: str) -> None: ...


class _Locator(Protocol):
    async def fill(self, value: str) -> None: ...

    async def scroll_into_view_if_needed(self) -> None: ...


class _Page(BrowserPage, Protocol):
    url: str
    mouse: _Mouse
    keyboard: _Keyboard

    async def goto(self, url: str, *, wait_until: str) -> object: ...

    async def set_viewport_size(self, size: dict[str, int]) -> None: ...

    async def close(self) -> None: ...

    def get_by_test_id(self, target: str) -> _Locator: ...


class _Context(Protocol):
    async def route(self, pattern: str, handler: Callable[[_Route], object]) -> None: ...

    async def new_page(self) -> _Page: ...

    def on(self, event: str, handler: Callable[[_Page], None]) -> None: ...

    async def close(self) -> None: ...


class _Browser(Protocol):
    async def new_context(self, **options: object) -> _Context: ...


def _loopback_origin(value: str) -> str:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise EnvironmentUnavailableError("local preview origin is malformed") from None
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or port is None
        or value != f"http://{parsed.hostname}:{port}"
    ):
        raise EnvironmentUnavailableError("local preview requires one exact loopback HTTP origin")
    return value


def _is_same_origin(url: str, origin: str) -> bool:
    try:
        candidate = urlsplit(url)
        allowed = urlsplit(origin)
        return (
            candidate.scheme == allowed.scheme
            and candidate.hostname == allowed.hostname
            and candidate.port == allowed.port
            and candidate.username is None
            and candidate.password is None
        )
    except ValueError:
        return False


@dataclass
class _Session:
    origin: str
    subject: EvidenceSubject
    context: _Context
    page: _Page | None
    next_step: int = 0
    egress_attempted: bool = False
    popup_attempted: bool = False


class LocalBrowserProvider:
    """Execute validated UI DTOs in one isolated Playwright browser context."""

    def __init__(self, browser: _Browser, collector: BrowserEvidenceCollector) -> None:
        self._browser = browser
        self._collector = collector
        self._sessions: dict[str, _Session] = {}

    async def open_session(self, environment: EnvironmentHandle, subject: EvidenceSubject) -> str:
        if not is_browser_subject_for(environment, subject):
            raise EnvironmentUnavailableError("browser evidence subject does not match environment")
        origin = _loopback_origin(environment.preview_origin)
        try:
            context = await self._browser.new_context(
                viewport={"width": 1280, "height": 720},
                service_workers="block",
                accept_downloads=False,
            )
        except Exception as exc:
            raise EnvironmentUnavailableError("local browser context could not open") from exc
        session = _Session(origin, subject, context, None)

        async def route_request(route: _Route) -> None:
            if not _is_same_origin(route.request.url, origin):
                session.egress_attempted = True
                await route.abort()
                return
            response = await route.fetch(max_redirects=0)
            if 300 <= response.status < 400:
                # Playwright routes only the first hop of a redirect chain.
                # Fulfilling a 3xx lets the browser follow later hops without
                # another route check, so this local adapter denies redirects.
                session.egress_attempted = True
                await route.abort()
                return
            await route.fulfill(response=response)

        try:
            await context.route("**/*", route_request)
            page = await context.new_page()
            session.page = page

            async def close_popup(popup: _Page) -> None:
                try:
                    await popup.close()
                except Exception:
                    # The context close below remains the final cleanup boundary.
                    pass

            def reject_popup(popup: _Page) -> None:
                session.popup_attempted = True
                asyncio.create_task(close_popup(popup))

            context.on("page", reject_popup)
        except BaseException as exc:
            try:
                await context.close()
            except Exception:
                pass
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise EnvironmentUnavailableError("local browser session could not open") from exc
        session_id = f"local-browser-{uuid4().hex}"
        self._sessions[session_id] = session
        return session_id

    async def perform(self, session_id: str, step_index: int, step: ActionStep) -> ActionRecord:
        session = self._sessions.get(session_id)
        if session is None or step_index != session.next_step:
            raise EnvironmentUnavailableError("browser session or step sequence is unavailable")
        page = session.page
        if page is None:
            raise EnvironmentUnavailableError("browser page is unavailable")
        if session.egress_attempted or session.popup_attempted:
            return ActionRecord(
                step_index=step_index,
                action=step.action,
                outcome="blocked",
                detail="Browser attempted to leave preview scope",
            )
        if step.action in {"test_api", "chat"}:
            return ActionRecord(
                step_index=step_index,
                action=step.action,
                outcome="blocked",
                detail="Action is outside the browser port",
            )
        if not isinstance(step, (NavigateStep, ResizeStep)) and not _is_same_origin(
            page.url, session.origin
        ):
            return ActionRecord(
                step_index=step_index,
                action=step.action,
                outcome="blocked",
                detail="Browser is outside its preview origin",
            )
        try:
            if isinstance(step, NavigateStep):
                await page.goto(session.origin + step.path, wait_until="domcontentloaded")
                record = ActionRecord(step_index=step_index, action="navigate", outcome="ok")
            elif isinstance(step, ResizeStep):
                await page.set_viewport_size({"width": step.width, "height": step.height})
                record = ActionRecord(step_index=step_index, action="resize", outcome="ok")
            elif isinstance(step, InspectStep):
                record = await self._collector.inspect(
                    page, step.target, session.subject, step_index
                )
            elif isinstance(step, ClickStep):
                record = await self._collector.click(page, step.target, session.subject, step_index)
            elif isinstance(step, CaptureStep):
                record = await self._collector.capture(page, session.subject, step_index)
            elif isinstance(step, ScrollStep):
                if step.target is not None:
                    await page.get_by_test_id(step.target).scroll_into_view_if_needed()
                await page.mouse.wheel(0, step.delta_y)
                record = ActionRecord(step_index=step_index, action="scroll", outcome="ok")
            elif isinstance(step, TypeStep):
                await page.get_by_test_id(step.target).fill(step.value)
                record = ActionRecord(step_index=step_index, action="type", outcome="ok")
            elif isinstance(step, PressStep):
                if step.key not in _PRESS_KEYS:
                    return ActionRecord(
                        step_index=step_index,
                        action="press",
                        outcome="blocked",
                        detail="Key is outside the browser action allowlist",
                    )
                await page.keyboard.press(step.key)
                record = ActionRecord(step_index=step_index, action="press", outcome="ok")
            else:
                raise EnvironmentUnavailableError("unrecognized browser action")
        except Exception as exc:
            if session.egress_attempted or session.popup_attempted:
                record = ActionRecord(
                    step_index=step_index,
                    action=step.action,
                    outcome="blocked",
                    detail="Browser attempted to leave its preview origin",
                )
            elif isinstance(exc, EnvironmentUnavailableError):
                raise
            else:
                raise EnvironmentUnavailableError("local browser action failed") from exc
        session.next_step += 1
        if (
            session.egress_attempted
            or session.popup_attempted
            or (page.url != "about:blank" and not _is_same_origin(page.url, session.origin))
        ):
            return record.model_copy(
                update={
                    "outcome": "blocked",
                    "detail": "Browser left or attempted to leave preview scope",
                }
            )
        return record

    async def close_session(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return
        try:
            await session.context.close()
        except Exception as exc:
            raise EnvironmentUnavailableError("local browser context could not close") from exc
        self._sessions.pop(session_id, None)
