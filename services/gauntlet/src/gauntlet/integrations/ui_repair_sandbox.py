"""Fresh local builds for one registered synthetic UI head and its approved CSS fix.

This is local process isolation, NOT Daytona or a hostile-code sandbox. The
operator supplies a trusted standalone Cartwheel repository and npm dependency
cache. No dependencies are installed and no package scripts or model commands
are executed. Approval is enforced by the calling repair coordinator.
"""

import asyncio
import os
import re
import shutil
import signal
import socket
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

from gauntlet.contracts import ReplayMode
from gauntlet.ports.errors import EnvironmentUnavailableError
from gauntlet.ports.sandbox import EnvironmentHandle

from .fixture_identity import verify_fixture_build_receipt
from .tool_world import RevisionCheckoutSandbox

_CSS_PATH = "src/components/FloatingHelp.module.css"
_SHA = re.compile(r"[0-9a-f]{40}\Z")


async def _settle[T](task: asyncio.Task[T]) -> tuple[T, bool]:
    """Finish resource acquisition/cleanup even under repeated cancellation."""
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    return task.result(), cancelled


@dataclass
class _Active:
    handle: EnvironmentHandle
    process: asyncio.subprocess.Process


class LocalUIRepairSandbox:
    label = "local_ui_repair"

    def __init__(
        self,
        repository: Path,
        *,
        target_id: str,
        fixture_id: str,
        fixture_checksum: str,
        head_sha: str,
        dependency_cache: Path,
        build_timeout_seconds: float = 180,
        startup_timeout_seconds: float = 30,
    ) -> None:
        if not _SHA.fullmatch(head_sha) or not re.fullmatch(r"[0-9a-f]{64}", fixture_checksum):
            raise ValueError("registered head and checksum must be full hashes")
        if not 0 < build_timeout_seconds <= 300 or not 0 < startup_timeout_seconds <= 60:
            raise ValueError("build and startup timeouts must be bounded")
        try:
            self._repository = repository.resolve(strict=True)
            self._cache = dependency_cache.resolve(strict=True)
        except OSError as exc:
            raise EnvironmentUnavailableError(
                "local repository or dependency cache is missing"
            ) from exc
        next_cli = self._cache / "next/dist/bin/next"
        if not next_cli.is_file() or not next_cli.resolve().is_relative_to(self._cache):
            raise EnvironmentUnavailableError(
                "explicit standalone Next dependency cache is required"
            )
        binaries = {name: shutil.which(name) for name in ("node", "git", "cp")}
        if any(value is None for value in binaries.values()):
            raise EnvironmentUnavailableError("local UI repair needs node, git and cp")
        self._node = str(Path(str(binaries["node"])).resolve())
        self._git = str(Path(str(binaries["git"])).resolve())
        self._cp = str(Path(str(binaries["cp"])).resolve())
        self._env = {
            "PATH": os.pathsep.join(
                dict.fromkeys(
                    (str(Path(self._node).parent), str(Path(self._git).parent), "/usr/bin", "/bin")
                )
            ),
            "NEXT_TELEMETRY_DISABLED": "1",
            "NODE_ENV": "production",
            "NODE_OPTIONS": "--max-old-space-size=2048",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
        }
        self._head = head_sha
        self._patched: str | None = None
        self._checksum = fixture_checksum
        self._build_timeout = build_timeout_seconds
        self._startup_timeout = startup_timeout_seconds
        self._exports = RevisionCheckoutSandbox(
            self._repository,
            target_id=target_id,
            fixture_id=fixture_id,
            fixture_checksum=fixture_checksum,
            allowed_shas=frozenset({head_sha}),
        )
        self._active: dict[str, _Active] = {}
        self._lock = asyncio.Lock()

    @property
    def active_environment_ids(self) -> tuple[str, ...]:
        return tuple(self._active)

    def allow(self, source_sha: str) -> None:
        """Called only after hash approval; register exactly one CSS-only descendant."""
        if not _SHA.fullmatch(source_sha) or source_sha == self._head:
            raise EnvironmentUnavailableError("patched revision must be a new full SHA")
        if self._patched is not None and source_sha != self._patched:
            raise EnvironmentUnavailableError("only one approved patched revision is allowed")
        try:
            subprocess.run(
                [
                    self._git,
                    "-C",
                    str(self._repository),
                    "merge-base",
                    "--is-ancestor",
                    self._head,
                    source_sha,
                ],
                env=self._env,
                check=True,
                capture_output=True,
                timeout=10,
            )
            changed = subprocess.run(
                [
                    self._git,
                    "-C",
                    str(self._repository),
                    "diff",
                    "--no-ext-diff",
                    "--no-textconv",
                    "--name-only",
                    self._head,
                    source_sha,
                    "--",
                ],
                env=self._env,
                check=True,
                capture_output=True,
                timeout=10,
                text=True,
            )
            if changed.stdout.splitlines() != [_CSS_PATH]:
                raise EnvironmentUnavailableError(
                    "approved UI patch must change only the registered CSS"
                )
        except (OSError, subprocess.SubprocessError) as exc:
            raise EnvironmentUnavailableError("patched revision could not be verified") from exc
        self._patched = source_sha
        self._exports.allow(source_sha)

    def root_of(self, environment_id: str) -> Path:
        return self._exports.root_of(environment_id)

    @staticmethod
    async def _stop(process: asyncio.subprocess.Process) -> None:
        # The group also covers Next workers or descendants surviving their parent.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await process.wait()

    async def _start(self, argv: list[str], root: Path) -> asyncio.subprocess.Process:
        process, cancelled = await _settle(
            asyncio.create_task(
                asyncio.create_subprocess_exec(
                    *argv,
                    cwd=root,
                    env=self._env,
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                    start_new_session=True,
                )
            )
        )
        if cancelled:
            await _settle(asyncio.create_task(self._stop(process)))
            raise asyncio.CancelledError
        return process

    async def _command(self, argv: list[str], root: Path, timeout: float) -> None:
        process = await self._start(argv, root)
        try:
            async with asyncio.timeout(timeout):
                if await process.wait() != 0:
                    raise EnvironmentUnavailableError("local UI build command failed")
        finally:
            _, cancelled = await _settle(asyncio.create_task(self._stop(process)))
            if cancelled:
                raise asyncio.CancelledError

    async def _cleanup(
        self, environment_id: str, process: asyncio.subprocess.Process | None
    ) -> None:
        async def clean() -> None:
            try:
                if process is not None:
                    await self._stop(process)
            finally:
                await self._exports.destroy(environment_id)

        _, cancelled = await _settle(asyncio.create_task(clean()))
        if cancelled:
            raise asyncio.CancelledError

    async def create(
        self, *, target_id: str, source_sha: str, fixture_id: str, mode: ReplayMode
    ) -> EnvironmentHandle:
        async with self._lock:
            if len(self._active) >= 2:
                raise EnvironmentUnavailableError("local UI repair environment limit reached")
            handle, cancelled = await _settle(
                asyncio.create_task(
                    self._exports.create(
                        target_id=target_id, source_sha=source_sha, fixture_id=fixture_id, mode=mode
                    )
                )
            )
            if cancelled:
                await self._cleanup(handle.environment_id, None)
                raise asyncio.CancelledError
            root = self.root_of(handle.environment_id)
            server: asyncio.subprocess.Process | None = None
            try:
                # A shallow local-only Git identity lets the fixture's existing clean-
                # checkout build receipt embed the real approved commit unchanged.
                await self._command([self._git, "init", "-q"], root, 10)
                await self._command(
                    [
                        self._git,
                        "-c",
                        "core.hooksPath=/dev/null",
                        "-c",
                        "protocol.allow=never",
                        "-c",
                        "protocol.file.allow=always",
                        "fetch",
                        "-q",
                        "--no-tags",
                        "--no-recurse-submodules",
                        "--depth=1",
                        str(self._repository),
                        source_sha,
                    ],
                    root,
                    30,
                )
                await self._command(
                    [self._git, "-c", "core.hooksPath=/dev/null", "reset", "--mixed", source_sha],
                    root,
                    10,
                )
                await self._command(
                    [self._cp, "-R", str(self._cache), str(root / "node_modules")], root, 60
                )
                cli = str(root / "node_modules/next/dist/bin/next")
                await self._command([self._node, cli, "build"], root, self._build_timeout)
                with socket.socket() as port_socket:
                    port_socket.bind(("127.0.0.1", 0))
                    port = port_socket.getsockname()[1]
                handle = replace(handle, preview_origin=f"http://127.0.0.1:{port}")
                server = await self._start(
                    [self._node, cli, "start", "--hostname", "127.0.0.1", "-p", str(port)], root
                )
                async with asyncio.timeout(self._startup_timeout):
                    while True:
                        if server.returncode is not None:
                            raise EnvironmentUnavailableError(
                                "local UI server exited before readiness"
                            )
                        try:
                            await verify_fixture_build_receipt(handle.preview_origin, source_sha)
                            break
                        except EnvironmentUnavailableError:
                            await asyncio.sleep(0.1)
                self._active[handle.environment_id] = _Active(handle, server)
                return handle
            except BaseException as exc:
                await self._cleanup(handle.environment_id, server)
                if isinstance(exc, (TimeoutError, OSError)):
                    raise EnvironmentUnavailableError("local UI build or startup failed") from exc
                raise

    async def verify_fixture(self, environment_id: str, expected_checksum: str) -> bool:
        active = self._active.get(environment_id)
        if (
            active is None
            or expected_checksum != self._checksum
            or active.process.returncode is not None
        ):
            return False
        try:
            await verify_fixture_build_receipt(
                active.handle.preview_origin, active.handle.source_sha
            )
        except EnvironmentUnavailableError:
            return False
        return await self._exports.verify_fixture(environment_id, expected_checksum)

    async def destroy(self, environment_id: str) -> None:
        active = self._active.pop(environment_id, None)
        await self._cleanup(environment_id, active.process if active is not None else None)
