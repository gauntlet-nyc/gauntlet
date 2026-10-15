"""Finish all live-smoke resource cleanup before returning a sanitized report."""

import asyncio
from dataclasses import dataclass
from typing import Protocol


class BrowserCleanup(Protocol):
    pending_cleanup_ids: tuple[str, ...]

    async def retry_pending_cleanup(self) -> None: ...


class SandboxCleanup(Protocol):
    pending_cleanup_ids: tuple[str, ...]

    async def destroy(self, environment_id: str) -> None: ...


class AnchorCleanup(BrowserCleanup, Protocol):
    async def close(self) -> None: ...


class RuntimeCleanup(Protocol):
    async def close(self) -> None: ...


@dataclass(frozen=True)
class CleanupResult:
    errors: tuple[str, ...]
    cancelled: bool


async def finish_smoke_resources(
    browser: BrowserCleanup | None,
    sandbox: SandboxCleanup | None,
    anchor: AnchorCleanup | None,
    daytona: RuntimeCleanup | None,
) -> CleanupResult:
    """Attempt every release even if one fails or the caller is cancelled."""

    async def release_all() -> tuple[str, ...]:
        errors: list[str] = []
        if browser is not None:
            try:
                await browser.retry_pending_cleanup()
            except (Exception, asyncio.CancelledError):
                errors.append("browser_cleanup")
        if sandbox is not None:
            for environment_id in sandbox.pending_cleanup_ids:
                try:
                    await sandbox.destroy(environment_id)
                except (Exception, asyncio.CancelledError):
                    errors.append("sandbox_cleanup")
        if anchor is not None:
            try:
                await anchor.retry_pending_cleanup()
            except (Exception, asyncio.CancelledError):
                errors.append("anchor_session_cleanup")
            try:
                await anchor.close()
            except (Exception, asyncio.CancelledError):
                errors.append("anchor_runtime_cleanup")
        if daytona is not None:
            try:
                await daytona.close()
            except (Exception, asyncio.CancelledError):
                errors.append("daytona_runtime_cleanup")
        return tuple(errors)

    cleanup = asyncio.create_task(release_all())
    cancelled = False
    while not cleanup.done():
        try:
            await asyncio.shield(cleanup)
        except asyncio.CancelledError:
            cancelled = True
    return CleanupResult(errors=cleanup.result(), cancelled=cancelled)
