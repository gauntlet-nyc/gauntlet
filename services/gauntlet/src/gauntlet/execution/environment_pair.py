"""Keep base and head Gate environments equivalent and scoped to one run."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from gauntlet.contracts import ChangeRequest
from gauntlet.ports.errors import EnvironmentUnavailableError
from gauntlet.ports.sandbox import EnvironmentHandle, SandboxProvider


@dataclass(frozen=True)
class GateEnvironmentPair:
    base: EnvironmentHandle
    head: EnvironmentHandle


@asynccontextmanager
async def gate_environment_pair(
    sandbox: SandboxProvider, change: ChangeRequest, expected_checksum: str
) -> AsyncIterator[GateEnvironmentPair]:
    """Yield verified base/head handles; release both on exit or partial failure."""
    if change.base_sha == change.head_sha:
        raise ValueError("Gate comparison requires different base and head revisions")
    handles: list[EnvironmentHandle] = []
    try:
        for source_sha in (change.base_sha, change.head_sha):
            handle = await sandbox.create(
                target_id=change.target_id,
                source_sha=source_sha,
                fixture_id=change.fixture_id,
                mode="gate_compare",
            )
            handles.append(handle)
            if (
                handle.target_id != change.target_id
                or handle.source_sha != source_sha
                or handle.fixture_id != change.fixture_id
                or handle.fixture_checksum != expected_checksum
                or (len(handles) == 2 and handle.environment_id == handles[0].environment_id)
            ):
                raise EnvironmentUnavailableError("Gate environment identity or fixture differs")
        for handle in handles:
            try:
                verified = await sandbox.verify_fixture(handle.environment_id, expected_checksum)
            except Exception as exc:
                raise EnvironmentUnavailableError("Gate fixture verification failed") from exc
            if not verified:
                raise EnvironmentUnavailableError("Gate fixture verification failed")
        yield GateEnvironmentPair(base=handles[0], head=handles[1])
    finally:

        async def destroy_all() -> None:
            cleanup_error: BaseException | None = None
            for handle in reversed(handles):
                try:
                    await sandbox.destroy(handle.environment_id)
                except (Exception, asyncio.CancelledError) as exc:
                    cleanup_error = cleanup_error or exc
            if cleanup_error is not None:
                raise EnvironmentUnavailableError(
                    "Gate environment cleanup failed"
                ) from cleanup_error

        cleanup = asyncio.create_task(destroy_all())
        cancelled_during_cleanup = False
        while not cleanup.done():
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                cancelled_during_cleanup = True
        cleanup.result()
        if cancelled_during_cleanup:
            raise asyncio.CancelledError
