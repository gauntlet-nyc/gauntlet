"""B-01b: registered snapshots must prove source and fixture state before use."""

import asyncio
import hashlib
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from types import SimpleNamespace

import pytest

from gauntlet.integrations.daytona import (
    DaytonaSandboxProvider,
    RegisteredSnapshot,
    RegisteredTarget,
)
from gauntlet.integrations.daytona.provider import DEFAULT_PREVIEW_TTL_SECONDS
from gauntlet.integrations.daytona.sdk import HttpxHealthProbe, SdkDaytonaRuntime, SdkSandbox
from gauntlet.planning import PlanningLimits
from gauntlet.ports.errors import EnvironmentUnavailableError

BASE = "a" * 40
HEAD = "b" * 40
FIXTURE_BYTES = b'{"synthetic_owners":["alice","bob"],"orders":[]}'
FIXTURE_DIGEST = hashlib.sha256(FIXTURE_BYTES).hexdigest()
TEMPLATE_CHECKSUM = "c" * 64


class FakeSandbox:
    def __init__(self, sandbox_id: str, source_sha: str = BASE) -> None:
        self.id = sandbox_id
        self.source_sha_result = source_sha
        self.fixture_bytes_result = FIXTURE_BYTES
        self.preview = "https://3100-token.proxy.daytona.work"
        self.source_reads = 0
        self.fixture_reads = 0
        self.start_calls: list[tuple[str, int]] = []
        self.fail_start = False

    async def checkout_sha(self, repo_path: str) -> str:
        assert repo_path == "/workspace/cartwheel"
        self.source_reads += 1
        return self.source_sha_result

    async def read_file(self, path: str) -> bytes:
        assert path == "/workspace/cartwheel/fixture-state.json"
        self.fixture_reads += 1
        return self.fixture_bytes_result

    async def start_cartwheel(self, repo_path: str, port: int) -> None:
        assert self.source_reads and self.fixture_reads
        self.start_calls.append((repo_path, port))
        if self.fail_start:
            raise RuntimeError("secret provider startup detail")

    async def signed_preview_origin(self, port: int, expires_in_seconds: int) -> str:
        assert port == 3100 and expires_in_seconds == DEFAULT_PREVIEW_TTL_SECONDS
        assert self.start_calls == [("/workspace/cartwheel", 3100)]
        return self.preview


class FakeRuntime:
    def __init__(self) -> None:
        self.created: list[str] = []
        self.deleted: list[str] = []
        self.sandboxes: dict[str, FakeSandbox] = {}
        self.fail_delete = False
        self.next_sandbox = FakeSandbox("daytona-1")

    async def create(self, snapshot: str, timeout: float) -> FakeSandbox:
        assert timeout == 20
        self.created.append(snapshot)
        self.sandboxes[self.next_sandbox.id] = self.next_sandbox
        return self.next_sandbox

    async def delete(self, sandbox: FakeSandbox, timeout: float) -> None:
        assert timeout == 10
        if self.fail_delete:
            raise RuntimeError("simulated provider deletion failure")
        self.deleted.append(sandbox.id)
        self.sandboxes.pop(sandbox.id, None)


class FakeHealth:
    def __init__(self, ready: bool = True) -> None:
        self.ready = ready
        self.calls = 0

    async def check(self, origin: str, path: str) -> bool:
        assert origin == "https://3100-token.proxy.daytona.work"
        assert path == "/checkout"
        self.calls += 1
        return self.ready


def target() -> RegisteredTarget:
    return RegisteredTarget(
        target_id="cartwheel-fixture",
        fixture_id="baseline-v1",
        fixture_checksum=TEMPLATE_CHECKSUM,
        fixture_state_digest=FIXTURE_DIGEST,
        fixture_state_path="/workspace/cartwheel/fixture-state.json",
        repo_path="/workspace/cartwheel",
        preview_port=3100,
        preview_domain_suffix=".proxy.daytona.work",
        ready_path="/checkout",
        startup_profile="cartwheel_next_v1",
        snapshots=(
            RegisteredSnapshot(
                source_sha=BASE, snapshot="cartwheel-base-v1", image_digest="d" * 64
            ),
            RegisteredSnapshot(
                source_sha=HEAD, snapshot="cartwheel-head-v1", image_digest="d" * 64
            ),
        ),
    )


def provider(
    runtime: FakeRuntime, health: FakeHealth | None = None, *, ready_timeout: float = 0.03
) -> DaytonaSandboxProvider:
    return DaytonaSandboxProvider(
        runtime,
        {"cartwheel-fixture": target()},
        health or FakeHealth(),
        create_timeout=20,
        ready_timeout=ready_timeout,
        delete_timeout=10,
        poll_interval=0.005,
    )


def test_unknown_target_and_revision_never_create() -> None:
    async def scenario() -> None:
        runtime = FakeRuntime()
        adapter = provider(runtime)
        for target_id, source_sha, fixture_id in (
            ("unknown", BASE, "baseline-v1"),
            ("cartwheel-fixture", "e" * 40, "baseline-v1"),
            ("cartwheel-fixture", BASE, "other-fixture"),
        ):
            with pytest.raises(EnvironmentUnavailableError):
                await adapter.create(
                    target_id=target_id,
                    source_sha=source_sha,
                    fixture_id=fixture_id,
                    mode="gate_compare",
                )
        assert runtime.created == []

    asyncio.run(scenario())


def test_health_probe_requires_real_200_without_following_redirect() -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/ready":
                self.send_response(200)
            else:
                self.send_response(302)
                self.send_header("Location", "/ready")
            self.end_headers()

        def log_message(self, *_args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:

        async def scenario() -> None:
            probe = HttpxHealthProbe()
            origin = f"http://127.0.0.1:{server.server_port}"
            assert await probe.check(origin, "/ready")
            assert not await probe.check(origin, "/redirect")

        asyncio.run(scenario())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_created_environment_rechecks_fixture_and_cleans_up() -> None:
    async def scenario() -> None:
        runtime = FakeRuntime()
        health = FakeHealth()
        adapter = provider(runtime, health)
        environment = await adapter.create(
            target_id="cartwheel-fixture",
            source_sha=BASE,
            fixture_id="baseline-v1",
            mode="gate_compare",
        )
        assert runtime.created == ["cartwheel-base-v1"]
        assert environment.environment_id == "daytona-1"
        assert environment.source_sha == BASE
        assert environment.fixture_checksum == TEMPLATE_CHECKSUM
        assert environment.preview_origin == runtime.next_sandbox.preview
        assert runtime.next_sandbox.start_calls == [("/workspace/cartwheel", 3100)]
        assert health.calls == 1
        assert await adapter.verify_fixture(environment.environment_id, TEMPLATE_CHECKSUM)
        runtime.next_sandbox.fixture_bytes_result = b"tampered"
        assert not await adapter.verify_fixture(environment.environment_id, TEMPLATE_CHECKSUM)
        await adapter.destroy(environment.environment_id)
        await adapter.destroy(environment.environment_id)
        assert runtime.deleted == ["daytona-1"]

    asyncio.run(scenario())


def test_source_or_fixture_mismatch_deletes_partial_environment() -> None:
    async def scenario() -> None:
        for source_sha, fixture in ((HEAD, FIXTURE_BYTES), (BASE, b"wrong")):
            runtime = FakeRuntime()
            runtime.next_sandbox.source_sha_result = source_sha
            runtime.next_sandbox.fixture_bytes_result = fixture
            with pytest.raises(EnvironmentUnavailableError):
                await provider(runtime).create(
                    target_id="cartwheel-fixture",
                    source_sha=BASE,
                    fixture_id="baseline-v1",
                    mode="gate_compare",
                )
            assert runtime.deleted == ["daytona-1"]
            assert runtime.next_sandbox.start_calls == []

    asyncio.run(scenario())


def test_unready_preview_times_out_and_deletes() -> None:
    async def scenario() -> None:
        runtime = FakeRuntime()
        health = FakeHealth(ready=False)
        with pytest.raises(EnvironmentUnavailableError):
            await provider(runtime, health).create(
                target_id="cartwheel-fixture",
                source_sha=BASE,
                fixture_id="baseline-v1",
                mode="gate_compare",
            )
        assert health.calls >= 1
        assert runtime.deleted == ["daytona-1"]

    asyncio.run(scenario())


def test_registered_startup_failure_cleans_without_requesting_preview() -> None:
    async def scenario() -> None:
        runtime = FakeRuntime()
        runtime.next_sandbox.fail_start = True
        with pytest.raises(EnvironmentUnavailableError) as error:
            await provider(runtime).create(
                target_id="cartwheel-fixture",
                source_sha=BASE,
                fixture_id="baseline-v1",
                mode="gate_compare",
            )
        assert "secret provider startup detail" not in str(error.value)
        assert runtime.next_sandbox.start_calls == [("/workspace/cartwheel", 3100)]
        assert runtime.deleted == ["daytona-1"]

    asyncio.run(scenario())


def test_invalid_preview_and_failed_delete_leave_retryable_cleanup() -> None:
    async def scenario() -> None:
        runtime = FakeRuntime()
        runtime.next_sandbox.preview = "https://attacker.invalid"
        runtime.fail_delete = True
        adapter = provider(runtime)
        with pytest.raises(EnvironmentUnavailableError):
            await adapter.create(
                target_id="cartwheel-fixture",
                source_sha=BASE,
                fixture_id="baseline-v1",
                mode="gate_compare",
            )
        assert adapter.pending_cleanup_ids == ("daytona-1",)
        runtime.fail_delete = False
        await adapter.destroy("daytona-1")
        assert adapter.pending_cleanup_ids == ()
        assert runtime.deleted == ["daytona-1"]

    asyncio.run(scenario())


def test_cancellation_during_readiness_deletes_sandbox() -> None:
    class StalledHealth(FakeHealth):
        def __init__(self) -> None:
            super().__init__()
            self.started = asyncio.Event()

        async def check(self, origin: str, path: str) -> bool:
            self.started.set()
            await asyncio.Event().wait()
            return False

    async def scenario() -> None:
        runtime = FakeRuntime()
        health = StalledHealth()
        adapter = provider(runtime, health)
        task = asyncio.create_task(
            adapter.create(
                target_id="cartwheel-fixture",
                source_sha=BASE,
                fixture_id="baseline-v1",
                mode="gate_compare",
            )
        )
        await health.started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert runtime.deleted == ["daytona-1"]

    asyncio.run(scenario())


def test_registration_rejects_unequal_images() -> None:
    original = target()
    with pytest.raises(ValueError, match="equivalent pinned image"):
        RegisteredTarget(
            **{
                **vars(original),
                "snapshots": (
                    original.snapshots[0],
                    RegisteredSnapshot(
                        source_sha=HEAD, snapshot="cartwheel-head-v1", image_digest="e" * 64
                    ),
                ),
            }
        )


def test_sdk_wrapper_uses_pinned_snapshot_and_waiting_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Params:
        def __init__(self, **values: object) -> None:
            self.values = values

    class Client:
        def __init__(self) -> None:
            self.params: Params | None = None
            self.deleted = False
            self.commands: list[tuple[str, str, int]] = []

        async def create(self, params: Params, *, timeout: float) -> object:
            assert timeout == 20
            self.params = params

            async def exec_command(command: str, *, cwd: str, timeout: int) -> object:
                self.commands.append((command, cwd, timeout))
                if command != "git rev-parse HEAD":
                    return SimpleNamespace(exit_code=0, result="")
                assert (cwd, timeout) == ("/workspace/cartwheel", 15)
                return SimpleNamespace(exit_code=0, result=BASE)

            async def download_file(path: str) -> bytes:
                assert path == "/workspace/cartwheel/fixture-state.json"
                return FIXTURE_BYTES

            async def preview(
                port: int, *, expires_in_seconds: int, request_timeout: int
            ) -> object:
                assert (port, expires_in_seconds, request_timeout) == (3100, 900, 15)
                return SimpleNamespace(url="https://3100-token.proxy.daytona.work")

            return SimpleNamespace(
                id="daytona-1",
                process=SimpleNamespace(exec=exec_command),
                fs=SimpleNamespace(download_file=download_file),
                create_signed_preview_url=preview,
            )

        async def delete(self, sandbox: SimpleNamespace, *, timeout: float, wait: bool) -> None:
            assert sandbox.id == "daytona-1"
            assert timeout == 10 and wait is True
            self.deleted = True

    monkeypatch.setitem(
        sys.modules, "daytona", SimpleNamespace(CreateSandboxFromSnapshotParams=Params)
    )
    monkeypatch.delenv("RUN_LIVE_INTEGRATIONS", raising=False)

    async def scenario() -> None:
        client = Client()
        runtime = SdkDaytonaRuntime(client)
        with pytest.raises(EnvironmentUnavailableError, match="not enabled"):
            await runtime.create("cartwheel-base-v1", 20)
        assert client.params is None
        monkeypatch.setenv("RUN_LIVE_INTEGRATIONS", "1")
        sandbox = await runtime.create("cartwheel-base-v1", 20)
        assert client.params is not None
        assert client.params.values == {
            "snapshot": "cartwheel-base-v1",
            "public": False,
            "network_block_all": True,
        }
        assert await sandbox.checkout_sha("/workspace/cartwheel") == BASE
        assert await sandbox.read_file("/workspace/cartwheel/fixture-state.json") == FIXTURE_BYTES
        await sandbox.start_cartwheel("/workspace/cartwheel", 3100)
        assert client.commands[-1] == (
            "test -s .next/BUILD_ID && test -x ./node_modules/.bin/next && "
            "(nohup ./node_modules/.bin/next start -p 3100 "
            ">/tmp/gauntlet-cartwheel-start.log 2>&1 </dev/null &)",
            "/workspace/cartwheel",
            20,
        )
        assert await sandbox.signed_preview_origin(3100, 900) == (
            "https://3100-token.proxy.daytona.work"
        )
        await runtime.delete(sandbox, 10)
        assert client.deleted

    asyncio.run(scenario())


def test_sdk_registered_startup_rejects_invalid_port_and_failed_command() -> None:
    class Process:
        def __init__(self) -> None:
            self.called = False

        async def exec(self, command: str, *, cwd: str, timeout: int) -> SimpleNamespace:
            self.called = True
            return SimpleNamespace(exit_code=1, result="secret output")

    async def scenario() -> None:
        process = Process()
        sandbox = SdkSandbox(SimpleNamespace(id="daytona-1", process=process))
        with pytest.raises(EnvironmentUnavailableError, match="port"):
            await sandbox.start_cartwheel("/workspace/cartwheel", 0)
        assert not process.called
        with pytest.raises(EnvironmentUnavailableError, match="registered startup failed") as error:
            await sandbox.start_cartwheel("/workspace/cartwheel", 3000)
        assert process.called
        assert "secret output" not in str(error.value)

    asyncio.run(scenario())


def test_preview_ttl_outlives_the_plan_budget() -> None:
    assert DEFAULT_PREVIEW_TTL_SECONDS > PlanningLimits().max_total_runtime_seconds
