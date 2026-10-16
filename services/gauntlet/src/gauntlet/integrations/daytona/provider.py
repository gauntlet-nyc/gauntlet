"""SandboxProvider backed by registered Daytona snapshots.

The registration is operator-owned configuration. Snapshot IDs, source SHAs,
fixture bytes and preview domain are fixed before a planner supplies any work.
No repository build command or model-provided shell is accepted here.
"""

import asyncio
import hashlib
import re
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

from gauntlet.contracts import ReplayMode
from gauntlet.ports.errors import EnvironmentUnavailableError
from gauntlet.ports.sandbox import EnvironmentHandle

_SHA = re.compile(r"[0-9a-f]{40}\Z")

DEFAULT_PREVIEW_TTL_SECONDS = 2400
"""Signed preview lifetime. Must outlive the whole plan budget (1800 s) plus startup margin."""
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class RegisteredSnapshot:
    source_sha: str
    snapshot: str
    image_digest: str

    def __post_init__(self) -> None:
        if not _SHA.fullmatch(self.source_sha) or not _DIGEST.fullmatch(self.image_digest):
            raise ValueError("registered snapshot requires pinned source and image digests")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", self.snapshot):
            raise ValueError("registered snapshot name is invalid")


@dataclass(frozen=True)
class RegisteredTarget:
    target_id: str
    fixture_id: str
    fixture_checksum: str
    fixture_state_digest: str
    fixture_state_path: str
    repo_path: str
    preview_port: int
    preview_domain_suffix: str
    ready_path: str
    startup_profile: str
    snapshots: tuple[RegisteredSnapshot, ...]

    def __post_init__(self) -> None:
        if not _DIGEST.fullmatch(self.fixture_checksum) or not _DIGEST.fullmatch(
            self.fixture_state_digest
        ):
            raise ValueError("target fixture digests must be SHA-256")
        if (
            not self.snapshots
            or len({entry.source_sha for entry in self.snapshots}) != len(self.snapshots)
            or len({entry.image_digest for entry in self.snapshots}) != 1
        ):
            raise ValueError("registered revisions require one equivalent pinned image digest")
        for path in (self.fixture_state_path, self.repo_path):
            if (
                not path.startswith("/")
                or ".." in path.split("/")
                or any(ord(char) < 0x20 for char in path)
            ):
                raise ValueError("registered sandbox paths must be absolute and safe")
        if type(self.preview_port) is not int or not 1 <= self.preview_port <= 65535:
            raise ValueError("preview port is invalid")
        if not re.fullmatch(r"\.[a-z0-9.-]+", self.preview_domain_suffix):
            raise ValueError("preview domain suffix is invalid")
        if self.startup_profile != "cartwheel_next_v1" or self.target_id != "cartwheel-fixture":
            raise ValueError("registered startup profile is unsupported")
        if (
            not self.ready_path.startswith("/")
            or self.ready_path.startswith("//")
            or urlsplit(self.ready_path).query
            or urlsplit(self.ready_path).fragment
        ):
            raise ValueError("readiness path must be a local URL path")


class DaytonaSandbox(Protocol):
    id: str

    async def checkout_sha(self, repo_path: str) -> str: ...

    async def read_file(self, path: str) -> bytes: ...

    async def start_cartwheel(self, repo_path: str, port: int) -> None: ...

    async def signed_preview_origin(self, port: int, expires_in_seconds: int) -> str: ...


class DaytonaRuntime(Protocol):
    async def create(self, snapshot: str, timeout: float) -> DaytonaSandbox: ...

    async def delete(self, sandbox: DaytonaSandbox, timeout: float) -> None: ...


class HealthProbe(Protocol):
    async def check(self, origin: str, path: str) -> bool: ...


def _preview_origin(value: str, suffix: str) -> str:
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        raise EnvironmentUnavailableError("Daytona preview URL is malformed") from None
    if (
        parsed.scheme != "https"
        or hostname is None
        or not hostname.endswith(suffix)
        or hostname == suffix[1:]
        or port is not None
        or value != f"https://{hostname}"
    ):
        raise EnvironmentUnavailableError("Daytona preview is outside the registered domain")
    return value


class DaytonaSandboxProvider:
    def __init__(
        self,
        runtime: DaytonaRuntime,
        targets: dict[str, RegisteredTarget],
        health: HealthProbe,
        *,
        create_timeout: float = 60,
        ready_timeout: float = 30,
        delete_timeout: float = 60,
        poll_interval: float = 0.5,
        preview_ttl_seconds: int = DEFAULT_PREVIEW_TTL_SECONDS,
    ) -> None:
        if min(create_timeout, ready_timeout, delete_timeout, poll_interval) <= 0:
            raise ValueError("Daytona timeouts must be positive")
        if preview_ttl_seconds < create_timeout + ready_timeout:
            raise ValueError("Daytona preview TTL must outlive environment startup")
        if any(key != value.target_id for key, value in targets.items()):
            raise ValueError("Daytona registration keys must match target IDs")
        self._runtime = runtime
        self._targets = dict(targets)
        self._health = health
        self._create_timeout = create_timeout
        self._ready_timeout = ready_timeout
        self._delete_timeout = delete_timeout
        self._poll_interval = poll_interval
        self._preview_ttl = preview_ttl_seconds
        self._active: dict[str, tuple[DaytonaSandbox, RegisteredTarget, str]] = {}
        self._pending_cleanup: set[str] = set()
        self._cleanup_tasks: dict[str, asyncio.Task[None]] = {}

    @property
    def pending_cleanup_ids(self) -> tuple[str, ...]:
        """Provider resource IDs requiring a later scoped cleanup retry."""
        return tuple(sorted(self._pending_cleanup))

    async def _matches_fixture(
        self, sandbox: DaytonaSandbox, target: RegisteredTarget, source_sha: str
    ) -> bool:
        observed_sha = (await sandbox.checkout_sha(target.repo_path)).strip()
        fixture_bytes = await sandbox.read_file(target.fixture_state_path)
        return (
            observed_sha == source_sha
            and 0 < len(fixture_bytes) <= 1_000_000
            and hashlib.sha256(fixture_bytes).hexdigest() == target.fixture_state_digest
        )

    async def _cleanup_failed_create(self, environment_id: str) -> bool:
        """Finish one bounded deletion despite further caller cancellation.

        Return whether another cancellation arrived while cleanup was running.
        Keep the resource visible for a scoped retry until deletion succeeds.
        """
        self._pending_cleanup.add(environment_id)
        cleanup = asyncio.create_task(self.destroy(environment_id))
        self._cleanup_tasks[environment_id] = cleanup

        def cleanup_finished(task: asyncio.Task[None]) -> None:
            if self._cleanup_tasks.get(environment_id) is task:
                self._cleanup_tasks.pop(environment_id)
            if not task.cancelled():
                task.exception()

        cleanup.add_done_callback(cleanup_finished)
        deadline = asyncio.get_running_loop().time() + self._delete_timeout
        cancelled = False
        while not cleanup.done():
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                break
            try:
                await asyncio.wait_for(asyncio.shield(cleanup), remaining)
            except asyncio.CancelledError:
                cancelled = True
            except (TimeoutError, EnvironmentUnavailableError):
                break
        if not cleanup.done():
            cleanup.cancel()
        else:
            try:
                cleanup.result()
            except (EnvironmentUnavailableError, asyncio.CancelledError):
                pass
        return cancelled

    async def create(
        self, *, target_id: str, source_sha: str, fixture_id: str, mode: ReplayMode
    ) -> EnvironmentHandle:
        target = self._targets.get(target_id)
        snapshot = (
            next((entry for entry in target.snapshots if entry.source_sha == source_sha), None)
            if target
            else None
        )
        if (
            target is None
            or target.fixture_id != fixture_id
            or snapshot is None
            or mode not in {"gate_compare", "fix_regression"}
        ):
            raise EnvironmentUnavailableError("target, fixture, revision or mode is not registered")
        try:
            sandbox = await self._runtime.create(snapshot.snapshot, self._create_timeout)
        except Exception as exc:
            raise EnvironmentUnavailableError("Daytona environment creation failed") from exc
        self._active[sandbox.id] = (sandbox, target, source_sha)
        try:
            if not await self._matches_fixture(sandbox, target, source_sha):
                raise EnvironmentUnavailableError("Daytona source or fixture state does not match")
            await sandbox.start_cartwheel(target.repo_path, target.preview_port)
            origin = _preview_origin(
                await sandbox.signed_preview_origin(target.preview_port, self._preview_ttl),
                target.preview_domain_suffix,
            )
            async with asyncio.timeout(self._ready_timeout):
                while not await self._health.check(origin, target.ready_path):
                    await asyncio.sleep(self._poll_interval)
            return EnvironmentHandle(
                environment_id=sandbox.id,
                target_id=target_id,
                source_sha=source_sha,
                fixture_id=fixture_id,
                fixture_checksum=target.fixture_checksum,
                preview_origin=origin,
            )
        except (Exception, asyncio.CancelledError) as exc:
            cancelled_during_cleanup = await self._cleanup_failed_create(sandbox.id)
            if isinstance(exc, asyncio.CancelledError) or cancelled_during_cleanup:
                raise asyncio.CancelledError() from exc
            raise EnvironmentUnavailableError(
                "Daytona environment failed validation or readiness"
            ) from exc

    async def verify_fixture(self, environment_id: str, expected_checksum: str) -> bool:
        active = self._active.get(environment_id)
        if active is None or environment_id in self._pending_cleanup:
            return False
        sandbox, target, source_sha = active
        if expected_checksum != target.fixture_checksum:
            return False
        try:
            return await self._matches_fixture(sandbox, target, source_sha)
        except Exception:
            return False

    async def destroy(self, environment_id: str) -> None:
        cleanup = self._cleanup_tasks.get(environment_id)
        if cleanup is not None and cleanup is not asyncio.current_task():
            try:
                await asyncio.wait_for(asyncio.shield(cleanup), self._delete_timeout)
            except TimeoutError:
                self._pending_cleanup.add(environment_id)
                raise EnvironmentUnavailableError(
                    "Daytona environment deletion is still in progress"
                ) from None
            except EnvironmentUnavailableError:
                pass
            except asyncio.CancelledError:
                if not cleanup.cancelled():
                    raise
        active = self._active.get(environment_id)
        if active is None:
            return
        sandbox = active[0]
        try:
            await self._runtime.delete(sandbox, self._delete_timeout)
        except asyncio.CancelledError:
            self._pending_cleanup.add(environment_id)
            raise
        except Exception as exc:
            self._pending_cleanup.add(environment_id)
            raise EnvironmentUnavailableError("Daytona environment deletion failed") from exc
        self._active.pop(environment_id, None)
        self._pending_cleanup.discard(environment_id)
