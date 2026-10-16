"""Bootstrap private Cartwheel cold snapshots from reviewed, pinned inputs.

Invoke as ``python -m scripts.provision_cartwheel_snapshots``. Default preflight
does not call Daytona. The paid path requires --execute, --authorize-spend,
RUN_LIVE_INTEGRATIONS=1, Cartwheel allowlisting and explicit credentials.
Captured snapshots remain unverified until a live restore/preview smoke.
"""

import argparse
import asyncio
import hashlib
import importlib.metadata
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Awaitable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast
from uuid import uuid4

from scripts.prepare_cartwheel_registration import prepare_registration

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "apps/cartwheel/fixture-manifest.v1.json"
STATE = ROOT / "apps/cartwheel/fixture/base/fixture-state.json"
BUILD = ROOT / "scripts/build_cartwheel_fixture.py"
REPO_PATH = "/workspace/cartwheel"
ENTRYPOINT = [
    "/bin/sh",
    "-c",
    "if test -f /workspace/cartwheel/.next/BUILD_ID; then "
    "cd /workspace/cartwheel && exec npm run start; else exec sleep infinity; fi",
]
VERIFIED_IMAGE = (
    "node:22-bookworm@sha256:0e5f906573693feaa1e21057ebdcfdb5bd5021f050b2dc7c9deceb629c7da2a8"
)
_SHA = re.compile(r"[0-9a-f]{40}\Z")


@dataclass(frozen=True)
class Inputs:
    base_sha: str
    head_sha: str
    image: str
    image_digest: str
    lock_sha256: str
    lock_bytes: bytes
    bundles: tuple[bytes, bytes]


class BootstrapCleanupError(RuntimeError):
    def __init__(self, pending: list[str]) -> None:
        super().__init__("Daytona bootstrap cleanup is incomplete")
        self.pending = tuple(pending)


class ExecuteResult(Protocol):
    exit_code: int
    result: str


class Process(Protocol):
    async def exec(
        self, command: str, cwd: str | None = None, timeout: int | None = None
    ) -> ExecuteResult: ...


class Filesystem(Protocol):
    async def upload_file(self, src: bytes, dst: str) -> None: ...
    async def download_file(self, path: str) -> bytes: ...


class Sandbox(Protocol):
    id: str
    process: Process
    fs: Filesystem

    async def stop(self, timeout: float = 60) -> None: ...
    async def create_snapshot(self, name: str, timeout: float = 60) -> None: ...


class Snapshot(Protocol):
    entrypoint: list[str] | None


class Snapshots(Protocol):
    async def create(self, params: object, *, timeout: float) -> Snapshot: ...
    async def get(self, name: str) -> Snapshot: ...
    async def delete(self, name: str) -> None: ...


class Client(Protocol):
    snapshot: Snapshots

    async def create(self, params: object, *, timeout: float) -> Sandbox: ...
    async def delete(self, sandbox: Sandbox, timeout: float = 60, wait: bool = False) -> None: ...
    async def close(self) -> None: ...


async def _settle_create[T](operation: Awaitable[T]) -> tuple[T, bool]:
    """Finish a paid create after cancellation so its resource ID is known."""
    task = asyncio.ensure_future(operation)
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    return task.result(), cancelled


def _bundle(repo: Path) -> bytes:
    memory = io.BytesIO()
    with tarfile.open(fileobj=memory, mode="w:gz") as archive:
        for path in sorted(repo.rglob("*")):
            if path.is_symlink():
                raise ValueError("generated fixture contains a symlink")
            if path.is_file():
                archive.add(path, arcname=path.relative_to(repo).as_posix(), recursive=False)
    return memory.getvalue()


def prepare_inputs(lockfile: Path, image: str) -> Inputs:
    """Check committed synthetic revisions and trusted npm lock before spend."""
    resolved_lock = lockfile.resolve()
    if any(
        resolved_lock.parts[index : index + 2] == ("bench", "private")
        for index in range(len(resolved_lock.parts) - 1)
    ):
        raise ValueError("private benchmark files are outside bootstrap scope")
    if image != VERIFIED_IMAGE:
        raise ValueError("Node image is not the verified pinned git/tar/npm image")
    manifest = json.loads(MANIFEST.read_text())
    state = STATE.read_bytes()
    baseline = json.loads(state)
    if (
        manifest.get("synthetic_only") is not True
        or manifest.get("target_id") != "cartwheel-fixture"
        or baseline.get("synthetic_only") is not True
        or baseline.get("fixture_id") != manifest.get("fixture_id")
    ):
        raise ValueError("committed Cartwheel fixture identity differs")
    refs = manifest.get("git_refs")
    if not isinstance(refs, dict):
        raise ValueError("Cartwheel revisions are missing")
    base, head = refs.get("base_sha"), refs.get("head_sha")
    if (
        not isinstance(base, str)
        or not isinstance(head, str)
        or not _SHA.fullmatch(base)
        or not _SHA.fullmatch(head)
        or base == head
    ):
        raise ValueError("Cartwheel revisions are invalid")
    lock_bytes = resolved_lock.read_bytes()
    if len(lock_bytes) > 5_000_000:
        raise ValueError("package lock is oversized")
    lock = json.loads(lock_bytes)
    package = json.loads((ROOT / "apps/cartwheel/fixture/base/package.json").read_text())
    packages = lock.get("packages") if isinstance(lock, dict) else None
    root_package = packages.get("") if isinstance(packages, dict) else None
    next_package = packages.get("node_modules/next") if isinstance(packages, dict) else None
    if (
        not isinstance(root_package, dict)
        or lock.get("lockfileVersion") not in {2, 3}
        or root_package.get("dependencies") != package.get("dependencies")
        or root_package.get("devDependencies") != package.get("devDependencies")
        or root_package.get("name") != package.get("name")
        or not isinstance(next_package, dict)
        or not isinstance(next_package.get("integrity"), str)
        or not next_package["integrity"].startswith("sha512-")
    ):
        raise ValueError("package lock does not match committed Cartwheel dependencies")
    with tempfile.TemporaryDirectory(prefix="gauntlet-cartwheel-build-") as directory:
        repo = Path(directory) / "cartwheel"
        built = subprocess.run(
            [sys.executable, str(BUILD), "--dest", str(repo)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        identity = json.loads(built.stdout)
        if (
            identity.get("base_sha") != base
            or identity.get("head_sha") != head
            or identity.get("fixture_checksum_sha256") != manifest.get("fixture_checksum_sha256")
        ):
            raise ValueError("rebuilt Cartwheel fixture does not match manifest")
        bundles: list[bytes] = []
        for sha in (base, head):
            subprocess.run(
                ["git", "checkout", "--detach", "--quiet", sha],
                cwd=repo,
                capture_output=True,
                check=True,
            )
            if (repo / "fixture-state.json").read_bytes() != state:
                raise ValueError("fixture state differs across revisions")
            bundles.append(_bundle(repo))
    return Inputs(
        base,
        head,
        image,
        VERIFIED_IMAGE.rsplit(":", 1)[1],
        hashlib.sha256(lock_bytes).hexdigest(),
        lock_bytes,
        (bundles[0], bundles[1]),
    )


async def _command(
    sandbox: Sandbox, command: str, timeout: int, *, cwd: str | None = REPO_PATH
) -> str:
    result = await sandbox.process.exec(command, cwd=cwd, timeout=timeout)
    if result.exit_code != 0:
        raise RuntimeError("Cartwheel snapshot seed command failed")
    return str(result.result).strip()


async def _cleanup(client: Client, sandboxes: list[Sandbox], snapshots: list[str]) -> list[str]:
    pending: list[str] = []
    for sandbox in reversed(sandboxes):
        try:
            await asyncio.wait_for(client.delete(sandbox, timeout=60, wait=True), 70)
        except Exception:
            pending.append(f"sandbox:{sandbox.id}")
    for name in reversed(snapshots):
        try:
            await asyncio.wait_for(client.snapshot.delete(name), 70)
        except Exception:
            pending.append(f"snapshot:{name}")
    return pending


async def provision(
    client: Client,
    inputs: Inputs,
    *,
    preview_domain_suffix: str,
    preview_port: int,
    output: Path | None = None,
) -> dict[str, object]:
    """Seed and capture two revisions, cleaning all temporary resources."""
    from daytona import CreateSandboxFromSnapshotParams, CreateSnapshotParams

    if output is not None:
        validate_output_path(output)

    prepare_registration(
        base_snapshot="cartwheel-b01p-validation-base",
        head_snapshot="cartwheel-b01p-validation-head",
        image_digest=inputs.image_digest,
        repo_path=REPO_PATH,
        preview_port=preview_port,
        preview_domain_suffix=preview_domain_suffix,
    )
    names = [f"cartwheel-b01p-{uuid4().hex[:20]}-{part}" for part in ("runtime", "base", "head")]
    sandboxes: list[Sandbox] = []
    finals: list[str] = []
    error: BaseException | None = None
    try:
        _, cancelled = await _settle_create(
            client.snapshot.create(
                CreateSnapshotParams(name=names[0], image=inputs.image, entrypoint=ENTRYPOINT),
                timeout=600,
            )
        )
        if cancelled:
            raise asyncio.CancelledError()
        if (await client.snapshot.get(names[0])).entrypoint != ENTRYPOINT:
            raise RuntimeError("Daytona runtime entrypoint differs")
        for index, sha in enumerate((inputs.base_sha, inputs.head_sha)):
            sandbox, cancelled = await _settle_create(
                client.create(
                    CreateSandboxFromSnapshotParams(
                        snapshot=names[0],
                        public=False,
                        domain_allow_list="registry.npmjs.org",
                        auto_delete_interval=120,
                    ),
                    timeout=120,
                )
            )
            sandboxes.append(sandbox)
            if cancelled:
                raise asyncio.CancelledError()
            await _command(sandbox, "mkdir -p /workspace/cartwheel", 20, cwd=None)
            await sandbox.fs.upload_file(inputs.bundles[index], "/tmp/cartwheel-source.tar.gz")
            await _command(
                sandbox, "tar -xzf /tmp/cartwheel-source.tar.gz -C /workspace/cartwheel", 60
            )
            await sandbox.fs.upload_file(inputs.lock_bytes, f"{REPO_PATH}/package-lock.json")
            if await _command(sandbox, "git rev-parse HEAD", 20) != sha:
                raise RuntimeError("Daytona checkout revision differs")
            if (
                await sandbox.fs.download_file(f"{REPO_PATH}/fixture-state.json")
                != STATE.read_bytes()
            ):
                raise RuntimeError("Daytona fixture state differs")
            await _command(sandbox, "npm ci --ignore-scripts --no-audit --no-fund", 600)
            await _command(sandbox, "npm run build", 600)
            await _command(sandbox, "test -s .next/BUILD_ID", 20)
            await sandbox.stop(timeout=60)
            finals.append(names[index + 1])
            _, cancelled = await _settle_create(
                sandbox.create_snapshot(names[index + 1], timeout=600)
            )
            if cancelled:
                raise asyncio.CancelledError()
            if (await client.snapshot.get(names[index + 1])).entrypoint != ENTRYPOINT:
                raise RuntimeError("Daytona captured snapshot lost its startup entrypoint")
    except BaseException as exc:
        error = exc
    cleanup_task = asyncio.create_task(_cleanup(client, sandboxes, [names[0]]))
    while not cleanup_task.done():
        try:
            await asyncio.shield(cleanup_task)
        except asyncio.CancelledError:
            if error is None:
                error = asyncio.CancelledError()
    pending = cleanup_task.result()
    if error is not None or pending:
        pending.extend(await _cleanup(client, [], finals))
        if pending:
            raise BootstrapCleanupError(pending) from error
        if error is not None:
            raise error
    try:
        registration = prepare_registration(
            base_snapshot=names[1],
            head_snapshot=names[2],
            image_digest=inputs.image_digest,
            repo_path=REPO_PATH,
            preview_port=preview_port,
            preview_domain_suffix=preview_domain_suffix,
        )
        if output is not None:
            created = False
            try:
                with output.open("x", encoding="utf-8") as stream:
                    created = True
                    stream.write(json.dumps(registration, indent=2) + "\n")
            except BaseException:
                if created:
                    output.unlink(missing_ok=True)
                raise
        return registration
    except BaseException:
        pending = await _cleanup(client, [], finals)
        if pending:
            raise BootstrapCleanupError(pending) from None
        raise


def _preflight(environment: dict[str, str], execute: bool, authorize_spend: bool) -> list[str]:
    missing = []
    if not execute:
        missing.append("execute")
    if not authorize_spend:
        missing.append("spend_authorization")
    if environment.get("RUN_LIVE_INTEGRATIONS") != "1":
        missing.append("live_opt_in")
    if "cartwheel-fixture" not in {
        item.strip() for item in environment.get("GAUNTLET_ALLOWED_TARGET_IDS", "").split(",")
    }:
        missing.append("cartwheel_target_allowlist")
    for name in ("DAYTONA_API_KEY", "DAYTONA_API_URL", "DAYTONA_TARGET"):
        if not environment.get(name) or environment[name].startswith("REPLACE_"):
            missing.append(name)
    if environment.get("DAYTONA_API_URL") and not environment["DAYTONA_API_URL"].startswith(
        "https://"
    ):
        missing.append("https_daytona_api_url")
    return missing


def validate_output_path(path: Path) -> Path:
    """Reserve registration for an existing directory outside every Git checkout."""
    if path.is_symlink():
        raise ValueError("registration output may not be a symlink")
    resolved = path.expanduser().resolve()
    if not resolved.parent.is_dir():
        raise ValueError("registration output parent must already exist")
    if resolved.exists():
        raise FileExistsError("registration output already exists")
    if any(
        (ancestor / ".git").exists() for ancestor in (resolved.parent, *resolved.parent.parents)
    ):
        raise ValueError("registration output must be outside every Git checkout")
    return resolved


async def _execute(inputs: Inputs, args: argparse.Namespace) -> None:
    from daytona import AsyncDaytona, DaytonaConfig

    client = AsyncDaytona(
        DaytonaConfig(
            api_key=os.environ["DAYTONA_API_KEY"],
            api_url=os.environ["DAYTONA_API_URL"],
            target=os.environ["DAYTONA_TARGET"],
        )
    )
    port = cast(Client, client)
    try:
        await provision(
            port,
            inputs,
            preview_domain_suffix=args.preview_domain_suffix,
            preview_port=args.preview_port,
            output=args.output,
        )
    finally:
        await port.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lockfile", type=Path, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--preview-domain-suffix", required=True)
    parser.add_argument("--preview-port", type=int, default=3000)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--authorize-spend", action="store_true")
    args = parser.parse_args()
    try:
        args.output = validate_output_path(args.output)
        inputs = prepare_inputs(args.lockfile, args.image)
        missing = _preflight(dict(os.environ), args.execute, args.authorize_spend)
        version = importlib.metadata.version("daytona")
        if version != "0.224.1":
            missing.append("pinned_daytona_sdk")
        if missing:
            print(
                json.dumps(
                    {
                        "status": "not_tested",
                        "missing": missing,
                        "sdk_version": version,
                        "base_sha": inputs.base_sha,
                        "head_sha": inputs.head_sha,
                        "lock_sha256": inputs.lock_sha256,
                    }
                )
            )
            return 2 if args.execute else 0
        asyncio.run(_execute(inputs, args))
        print(
            json.dumps(
                {
                    "status": "not_tested",
                    "snapshots_created": True,
                    "restore_smoke_verified": False,
                    "gate_status": "not_tested",
                    "sdk_version": version,
                    "base_sha": inputs.base_sha,
                    "head_sha": inputs.head_sha,
                    "lock_sha256": inputs.lock_sha256,
                }
            )
        )
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        print(
            json.dumps(
                {
                    "status": "environment_error",
                    "error_type": type(exc).__name__,
                    "gate_status": "not_tested",
                    "pending_cleanup_ids": exc.pending
                    if isinstance(exc, BootstrapCleanupError)
                    else (),
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
