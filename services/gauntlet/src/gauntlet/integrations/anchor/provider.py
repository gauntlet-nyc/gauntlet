"""Anchor browser sessions bound to signed Daytona preview origins.

The injected runtime owns cloud session creation. A separately configured
egress proxy must enforce the same origin outside Playwright's route guard.
"""

import asyncio
import re
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit
from uuid import uuid4

from gauntlet.contracts import ActionRecord, ActionStep, EvidenceSubject
from gauntlet.integrations.browser_evidence import BrowserEvidenceCollector
from gauntlet.integrations.local_browser import PlaywrightBrowser, ScopedPlaywrightProvider
from gauntlet.ports.browser import is_browser_subject_for
from gauntlet.ports.errors import EnvironmentUnavailableError
from gauntlet.ports.sandbox import EnvironmentHandle


class AnchorConnection(Protocol):
    browser: PlaywrightBrowser

    async def close(self) -> None: ...


class AnchorRuntime(Protocol):
    async def open(self) -> AnchorConnection: ...


def _preview_origin(value: str, suffix: str) -> str:
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        raise EnvironmentUnavailableError("cloud browser preview URL is malformed") from None
    if (
        parsed.scheme != "https"
        or hostname is None
        or not hostname.endswith(suffix)
        or hostname == suffix[1:]
        or port is not None
        or value != f"https://{hostname}"
    ):
        raise EnvironmentUnavailableError("cloud browser preview is outside registered domain")
    return value


@dataclass
class _Session:
    connection: AnchorConnection
    scoped: ScopedPlaywrightProvider
    scoped_id: str
    context_closed: bool = False


class AnchorBrowserProvider:
    """Typed browser port over an Anchor CDP browser and scoped context."""

    def __init__(
        self,
        runtime: AnchorRuntime,
        collector: BrowserEvidenceCollector,
        *,
        preview_domain_suffix: str,
    ) -> None:
        if not re.fullmatch(r"\.[a-z0-9.-]+", preview_domain_suffix):
            raise ValueError("preview domain suffix is invalid")
        self._runtime = runtime
        self._collector = collector
        self._suffix = preview_domain_suffix
        self._sessions: dict[str, _Session] = {}
        self._pending_cleanup: set[str] = set()
        self._orphans: dict[str, AnchorConnection] = {}

    @property
    def pending_cleanup_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._pending_cleanup | self._orphans.keys()))

    async def retry_pending_cleanup(self) -> None:
        for session_id in self.pending_cleanup_ids:
            orphan = self._orphans.get(session_id)
            if orphan is None:
                await self.close_session(session_id)
            else:
                try:
                    await orphan.close()
                except Exception as exc:
                    raise EnvironmentUnavailableError("Anchor orphan cleanup failed") from exc
                self._orphans.pop(session_id, None)

    async def open_session(self, environment: EnvironmentHandle, subject: EvidenceSubject) -> str:
        if not is_browser_subject_for(environment, subject):
            raise EnvironmentUnavailableError("browser evidence subject does not match environment")
        _preview_origin(environment.preview_origin, self._suffix)
        try:
            connection = await self._runtime.open()
        except Exception as exc:
            raise EnvironmentUnavailableError("Anchor browser session could not open") from exc
        scoped = ScopedPlaywrightProvider(
            connection.browser,
            self._collector,
            lambda value: _preview_origin(value, self._suffix),
        )
        try:
            scoped_id = await scoped.open_session(environment, subject)
        except (Exception, asyncio.CancelledError):
            close_task = asyncio.create_task(connection.close())
            # A second cancellation must not interrupt deletion of a paid session.
            while not close_task.done():
                try:
                    await asyncio.shield(close_task)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            try:
                close_task.result()
            except (Exception, asyncio.CancelledError):
                self._orphans[f"anchor-orphan-{uuid4().hex}"] = connection
            raise
        session_id = f"anchor-browser-{uuid4().hex}"
        self._sessions[session_id] = _Session(connection, scoped, scoped_id)
        return session_id

    async def perform(self, session_id: str, step_index: int, step: ActionStep) -> ActionRecord:
        session = self._sessions.get(session_id)
        if session is None or session_id in self._pending_cleanup:
            raise EnvironmentUnavailableError("Anchor browser session is unavailable")
        return await session.scoped.perform(session.scoped_id, step_index, step)

    async def close_session(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return
        try:
            if not session.context_closed:
                await session.scoped.close_session(session.scoped_id)
                session.context_closed = True
            await session.connection.close()
        except Exception as exc:
            self._pending_cleanup.add(session_id)
            raise EnvironmentUnavailableError("Anchor browser session could not close") from exc
        self._sessions.pop(session_id, None)
        self._pending_cleanup.discard(session_id)
