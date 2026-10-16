"""B-01p snapshot bootstrap uses only committed synthetic inputs offline."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts import provision_cartwheel_snapshots as bootstrap


def lockfile(tmp_path: Path) -> Path:
    package = json.loads((bootstrap.ROOT / "apps/cartwheel/fixture/base/package.json").read_text())
    path = tmp_path / "package-lock.json"
    path.write_text(
        json.dumps(
            {
                "name": package["name"],
                "lockfileVersion": 3,
                "packages": {
                    "": {
                        "name": package["name"],
                        "dependencies": package["dependencies"],
                        "devDependencies": package["devDependencies"],
                    },
                    "node_modules/next": {"version": "15.5.28"},
                    "node_modules/@next/swc-linux-x64-gnu": {
                        "version": "15.5.28",
                        "integrity": "sha512-linux-test",
                    },
                },
            }
        )
    )
    return path


def inputs(tmp_path: Path) -> bootstrap.Inputs:
    def fake_build(repo: Path, sha: str, image: str) -> None:
        assert image == bootstrap.VERIFIED_IMAGE
        assert len(sha) == 40
        assert (repo / "package-lock.json").is_file()
        (repo / ".next").mkdir(exist_ok=True)
        (repo / ".next/BUILD_ID").write_text(sha)

    return bootstrap.prepare_inputs(
        lockfile(tmp_path), bootstrap.VERIFIED_IMAGE, build_revision=fake_build
    )


class FakeProcess:
    def __init__(self, owner: "FakeSandbox") -> None:
        self.owner = owner

    async def exec(
        self, command: str, cwd: str | None = None, timeout: int | None = None
    ) -> SimpleNamespace:
        self.owner.calls.append((command, cwd, timeout))
        if command == self.owner.fail_command:
            return SimpleNamespace(exit_code=1, result="secret provider output")
        if command == "git rev-parse HEAD":
            return SimpleNamespace(exit_code=0, result=self.owner.sha)
        return SimpleNamespace(exit_code=0, result="")


class FakeFilesystem:
    def __init__(self, owner: "FakeSandbox") -> None:
        self.owner = owner

    async def upload_file(self, src: bytes, dst: str) -> None:
        self.owner.uploads.append((src, dst))

    async def upload_file_stream(self, source: bytes, remote_path: str) -> None:
        self.owner.uploads.append((source, remote_path))

    async def download_file(self, path: str) -> bytes:
        assert path == "/workspace/cartwheel/fixture-state.json"
        return bootstrap.STATE.read_bytes()


class FakeSandbox:
    def __init__(self, sha: str, number: int, fail_command: str | None) -> None:
        self.id = f"sandbox-{number}"
        self.sha = sha
        self.fail_command = fail_command
        self.calls: list[tuple[str, str | None, int | None]] = []
        self.uploads: list[tuple[bytes, str]] = []
        self.process = FakeProcess(self)
        self.fs = FakeFilesystem(self)
        self.stopped = False
        self.snapshot_name: str | None = None

    async def stop(self, timeout: float = 60) -> None:
        self.stopped = True

    async def create_snapshot(self, name: str, timeout: float = 60) -> None:
        assert self.stopped
        self.snapshot_name = name


class FakeSnapshots:
    def __init__(self, owner: "FakeClient") -> None:
        self.owner = owner
        self.created: list[object] = []
        self.deleted: list[str] = []

    async def create(self, params: object, *, timeout: float) -> SimpleNamespace:
        self.created.append(params)
        return SimpleNamespace(name=params.name)

    async def get(self, name: str) -> SimpleNamespace:
        return SimpleNamespace(name=name, entrypoint=bootstrap.ENTRYPOINT, state="active")

    async def delete(self, name: str) -> None:
        self.deleted.append(name)


class FakeClient:
    def __init__(
        self,
        source: bootstrap.Inputs,
        fail_command: str | None = None,
        fail_delete: bool = False,
    ) -> None:
        self.source = source
        self.fail_command = fail_command
        self.fail_delete = fail_delete
        self.snapshot = FakeSnapshots(self)
        self.sandboxes: list[FakeSandbox] = []
        self.deleted: list[str] = []
        self.params: list[object] = []

    async def create(self, params: object, *, timeout: float) -> FakeSandbox:
        self.params.append(params)
        number = len(self.sandboxes)
        sha = (self.source.base_sha, self.source.head_sha)[number]
        sandbox = FakeSandbox(sha, number, self.fail_command)
        self.sandboxes.append(sandbox)
        return sandbox

    async def delete(self, sandbox: FakeSandbox, timeout: float = 60, wait: bool = False) -> None:
        assert wait
        if self.fail_delete:
            raise RuntimeError("private provider cleanup error")
        self.deleted.append(sandbox.id)

    async def close(self) -> None:
        pass


def test_preflight_rebuilds_exact_fixture_and_checks_lock(tmp_path: Path) -> None:
    source = inputs(tmp_path)
    manifest = json.loads(bootstrap.MANIFEST.read_text())
    assert (source.base_sha, source.head_sha) == (
        manifest["git_refs"]["base_sha"],
        manifest["git_refs"]["head_sha"],
    )
    assert all(bundle.startswith(b"\x1f\x8b") for bundle in source.bundles)
    assert source.bundles[0] != source.bundles[1]
    assert "spend_authorization" in bootstrap._preflight({}, False, False)
    assert "live_opt_in" in bootstrap._preflight({}, False, False)


def test_unpinned_image_and_wrong_lock_rejected_before_provider(tmp_path: Path) -> None:
    path = lockfile(tmp_path)
    with pytest.raises(ValueError, match="private benchmark"):
        bootstrap.prepare_inputs(
            tmp_path / "bench/private/package-lock.json", bootstrap.VERIFIED_IMAGE
        )
    with pytest.raises(ValueError, match="verified pinned"):
        bootstrap.prepare_inputs(path, "node:22", build_revision=lambda *_: None)
    with pytest.raises(ValueError, match="verified pinned"):
        bootstrap.prepare_inputs(
            path,
            "node:22-bookworm-slim@sha256:"
            "c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392",
            build_revision=lambda *_: None,
        )
    raw = json.loads(path.read_text())
    raw["packages"][""]["dependencies"]["next"] = "untrusted"
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="package lock"):
        bootstrap.prepare_inputs(path, bootstrap.VERIFIED_IMAGE, build_revision=lambda *_: None)


def test_linux_swc_lock_entry_required_before_local_build(tmp_path: Path) -> None:
    path = lockfile(tmp_path)
    raw = json.loads(path.read_text())
    del raw["packages"]["node_modules/@next/swc-linux-x64-gnu"]
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="package lock"):
        bootstrap.prepare_inputs(path, bootstrap.VERIFIED_IMAGE, build_revision=lambda *_: None)


def test_local_build_must_preserve_reviewed_lock(tmp_path: Path) -> None:
    def changes_lock(repo: Path, _sha: str, _image: str) -> None:
        (repo / "package-lock.json").write_text("{}")
        (repo / ".next").mkdir()
        (repo / ".next/BUILD_ID").write_text("built")

    with pytest.raises(ValueError, match="changed the reviewed package lock"):
        bootstrap.prepare_inputs(
            lockfile(tmp_path), bootstrap.VERIFIED_IMAGE, build_revision=changes_lock
        )


def test_output_must_be_ready_and_outside_any_checkout(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="parent"):
        bootstrap.validate_output_path(tmp_path / "missing/registration.json")
    checkout = tmp_path / "other-checkout"
    checkout.mkdir()
    (checkout / ".git").write_text("gitdir: /tmp/unrelated-worktree")
    with pytest.raises(ValueError, match="outside every Git checkout"):
        bootstrap.validate_output_path(checkout / "registration.json")
    assert bootstrap.validate_output_path(tmp_path / "registration.json") == (
        tmp_path / "registration.json"
    )


def test_invalid_output_blocks_provider_creation(tmp_path: Path) -> None:
    source = inputs(tmp_path)
    client = FakeClient(source)
    with pytest.raises(ValueError, match="parent"):
        asyncio.run(
            bootstrap.provision(
                client,
                source,
                preview_domain_suffix=".proxy.daytona.work",
                preview_port=3000,
                output=tmp_path / "missing/registration.json",
            )
        )
    assert client.snapshot.created == []
    assert client.sandboxes == []


def test_offline_lifecycle_stops_before_snapshot_and_cleans_temporary_resources(
    tmp_path: Path,
) -> None:
    source = inputs(tmp_path)
    client = FakeClient(source)
    output = tmp_path / "registration.json"
    registration = asyncio.run(
        bootstrap.provision(
            client,
            source,
            preview_domain_suffix=".proxy.daytona.work",
            preview_port=3000,
            output=output,
        )
    )
    assert len(client.sandboxes) == 2
    assert all(sandbox.stopped and sandbox.snapshot_name for sandbox in client.sandboxes)
    assert all(
        ("test -s .next/BUILD_ID", bootstrap.REPO_PATH, 20) in sandbox.calls
        for sandbox in client.sandboxes
    )
    assert all(
        all(
            "npm ci" not in command and "npm run build" not in command
            for command, _, _ in sandbox.calls
        )
        for sandbox in client.sandboxes
    )
    assert all(
        param.network_block_all is True and param.domain_allow_list is None
        for param in client.params
    )
    assert all(param.auto_delete_interval == 20 for param in client.params)
    assert all(param.public is False for param in client.params)
    assert len(client.deleted) == 2
    assert len(client.snapshot.deleted) == 1
    assert registration["target_id"] == "cartwheel-fixture"
    assert json.loads(output.read_text()) == registration
    assert {entry["source_sha"] for entry in registration["snapshots"]} == {
        source.base_sha,
        source.head_sha,
    }


def test_seed_failure_deletes_created_resources_without_exposing_output(tmp_path: Path) -> None:
    source = inputs(tmp_path)
    client = FakeClient(source, fail_command="git status --porcelain")
    with pytest.raises(RuntimeError, match="seed command failed") as error:
        asyncio.run(
            bootstrap.provision(
                client, source, preview_domain_suffix=".proxy.daytona.work", preview_port=3000
            )
        )
    assert "secret" not in str(error.value)
    assert len(client.deleted) == 1
    assert len(client.snapshot.deleted) == 1


def test_cancellation_cleans_created_sandbox(tmp_path: Path) -> None:
    source = inputs(tmp_path)
    client = FakeClient(source)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def slow_create(params: object, *, timeout: float) -> FakeSandbox:
        sandbox = await FakeClient.create(client, params, timeout=timeout)
        entered.set()
        await release.wait()
        return sandbox

    client.create = slow_create  # type: ignore[method-assign]

    async def scenario() -> None:
        task = asyncio.create_task(
            bootstrap.provision(
                client, source, preview_domain_suffix=".proxy.daytona.work", preview_port=3000
            )
        )
        await entered.wait()
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert client.deleted == ["sandbox-0"]
        assert client.snapshot.deleted

    asyncio.run(scenario())


def test_cleanup_failure_reports_retryable_resource_ids(tmp_path: Path) -> None:
    source = inputs(tmp_path)
    client = FakeClient(source, fail_delete=True)
    with pytest.raises(bootstrap.BootstrapCleanupError) as error:
        asyncio.run(
            bootstrap.provision(
                client,
                source,
                preview_domain_suffix=".proxy.daytona.work",
                preview_port=3000,
                output=tmp_path / "registration.json",
            )
        )
    assert {"sandbox:sandbox-0", "sandbox:sandbox-1"} <= set(error.value.pending)
    assert "private" not in str(error.value)
    assert not (tmp_path / "registration.json").exists()
