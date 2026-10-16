"""Anchor browser sessions bound to signed Daytona preview origins.

The injected runtime owns cloud session creation. A separately configured
egress proxy must enforce the same origin outside Playwright's route guard.
"""

import asyncio
import math
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


@dataclass(frozen=True)
class AnchorSessionEvidence:
    """Provider facts to persist with the run: the recording reference and isolation mode."""

    browser_session_id: str
    anchor_session_id: str | None
    recording_id: str | None
    egress_isolation: str

    def as_payload(self) -> dict[str, str | bool | None]:
        """Flat scalars suitable for a `RunEvent.payload`."""
        return {
            "browser_session_id": self.browser_session_id,
            "anchor_session_id": self.anchor_session_id,
            "anchor_recording_id": self.recording_id,
            "egress_isolation": self.egress_isolation,
            "egress_isolation_weaker": self.egress_isolation != "custom_proxy",
        }


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
        cleanup_timeout_seconds: float = 20.0,
    ) -> None:
        if not re.fullmatch(r"\.[a-z0-9.-]+", preview_domain_suffix):
            raise ValueError("preview domain suffix is invalid")
        if isinstance(cleanup_timeout_seconds, bool) or not isinstance(
            cleanup_timeout_seconds, (int, float)
        ):
            raise ValueError("cleanup timeout must be finite and positive")
        try:
            cleanup_timeout_seconds = float(cleanup_timeout_seconds)
        except OverflowError:
            raise ValueError("cleanup timeout must be finite and positive") from None
        if not math.isfinite(cleanup_timeout_seconds) or cleanup_timeout_seconds <= 0:
            raise ValueError("cleanup timeout must be finite and positive")
        self._runtime = runtime
        self._collector = collector
        self._suffix = preview_domain_suffix
        self._cleanup_timeout_seconds = cleanup_timeout_seconds
        self._sessions: dict[str, _Session] = {}
        self._pending_cleanup: set[str] = set()
        self._orphans: dict[str, AnchorConnection] = {}
        self._orphan_close_tasks: dict[str, asyncio.Task[None]] = {}

    @property
    def pending_cleanup_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._pending_cleanup | self._orphans.keys()))

    def _track_orphan_close(self, orphan_id: str, task: asyncio.Task[None]) -> None:
        self._orphan_close_tasks[orphan_id] = task

        def settled(completed: asyncio.Task[None]) -> None:
            try:
                completed.result()
            except (Exception, asyncio.CancelledError):
                pass
            else:
                if self._orphan_close_tasks.get(orphan_id) is completed:
                    self._orphans.pop(orphan_id, None)
            if self._orphan_close_tasks.get(orphan_id) is completed:
                self._orphan_close_tasks.pop(orphan_id, None)

        task.add_done_callback(settled)

    async def retry_pending_cleanup(self) -> None:
        for session_id in self.pending_cleanup_ids:
            orphan = self._orphans.get(session_id)
            if orphan is None:
                await self.close_session(session_id)
            else:
                close_task = self._orphan_close_tasks.get(session_id)
                if close_task is not None:
                    if not close_task.done():
                        raise EnvironmentUnavailableError("Anchor orphan cleanup still in progress")
                    self._orphan_close_tasks.pop(session_id, None)
                    try:
                        close_task.result()
                    except (Exception, asyncio.CancelledError):
                        pass
                    else:
                        self._orphans.pop(session_id, None)
                        continue
                close_task = asyncio.create_task(orphan.close())
                self._track_orphan_close(session_id, close_task)
                try:
                    await asyncio.wait_for(
                        asyncio.shield(close_task), self._cleanup_timeout_seconds
                    )
                except asyncio.CancelledError:
                    raise
                except TimeoutError as exc:
                    close_task.cancel()
                    raise EnvironmentUnavailableError("Anchor orphan cleanup timed out") from exc
                except Exception as exc:
                    if self._orphan_close_tasks.get(session_id) is close_task:
                        self._orphan_close_tasks.pop(session_id, None)
                    raise EnvironmentUnavailableError("Anchor orphan cleanup failed") from exc
                if self._orphan_close_tasks.get(session_id) is close_task:
                    self._orphan_close_tasks.pop(session_id, None)
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
            # Daytona serves an interstitial warning page to browsers without this header.
            extra_http_headers={"X-Daytona-Skip-Preview-Warning": "true"},
        )
        caller_task = asyncio.current_task()
        caller_cancellations = caller_task.cancelling() if caller_task is not None else 0
        try:
            scoped_id = await scoped.open_session(environment, subject)
        except (Exception, asyncio.CancelledError) as open_error:
            close_task = asyncio.create_task(connection.close())
            loop = asyncio.get_running_loop()
            deadline = loop.time() + self._cleanup_timeout_seconds
            # Repeated caller cancellations cannot reset the cleanup deadline.
            while not close_task.done():
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                try:
                    await asyncio.wait_for(asyncio.shield(close_task), remaining)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            if close_task.done():
                try:
                    close_task.result()
                except (Exception, asyncio.CancelledError):
                    self._orphans[f"anchor-orphan-{uuid4().hex}"] = connection
            else:
                orphan_id = f"anchor-orphan-{uuid4().hex}"
                self._orphans[orphan_id] = connection
                self._track_orphan_close(orphan_id, close_task)
                close_task.cancel()
            if (
                isinstance(open_error, Exception)
                and caller_task is not None
                and caller_task.cancelling() > caller_cancellations
            ):
                raise asyncio.CancelledError() from None
            raise
        session_id = f"anchor-browser-{uuid4().hex}"
        self._sessions[session_id] = _Session(connection, scoped, scoped_id)
        return session_id

    def session_evidence(self, session_id: str) -> AnchorSessionEvidence:
        session = self._sessions.get(session_id)
        if session is None:
            raise EnvironmentUnavailableError("Anchor browser session is unavailable")
        connection = session.connection
        return AnchorSessionEvidence(
            browser_session_id=session_id,
            anchor_session_id=getattr(connection, "session_id", None),
            recording_id=getattr(connection, "recording_id", None),
            egress_isolation=getattr(connection, "egress_isolation", "unknown"),
        )

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
        except asyncio.CancelledError:
            self._pending_cleanup.add(session_id)
            raise
        except Exception as exc:
            self._pending_cleanup.add(session_id)
            raise EnvironmentUnavailableError("Anchor browser session could not close") from exc
        self._sessions.pop(session_id, None)
        self._pending_cleanup.discard(session_id)
