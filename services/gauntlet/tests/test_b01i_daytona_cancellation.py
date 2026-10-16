"""Cancellation must not abandon cleanup of a partially created sandbox."""

import asyncio
import hashlib

import pytest

from gauntlet.integrations.daytona.provider import (
    DaytonaSandboxProvider,
    RegisteredSnapshot,
    RegisteredTarget,
)
from gauntlet.ports.errors import EnvironmentUnavailableError

SHA = "a" * 40
FIXTURE = b"synthetic fixture"


class Sandbox:
    id = "sandbox-1"

    def __init__(self) -> None:
        self.verifying = asyncio.Event()

    async def checkout_sha(self, repo_path: str) -> str:
        self.verifying.set()
        await asyncio.Event().wait()
        return SHA

    async def read_file(self, path: str) -> bytes:
        return FIXTURE

    async def start_cartwheel(self, repo_path: str, port: int) -> None:
        assert (repo_path, port) == ("/workspace/repo", 3100)

    async def signed_preview_origin(self, port: int, expires_in_seconds: int) -> str:
        return "https://token.proxy.daytona.work"


class Runtime:
    def __init__(self) -> None:
        self.sandbox = Sandbox()
        self.deleting = asyncio.Event()
        self.finish_delete = asyncio.Event()
        self.delete_calls = 0
        self.deleted = False
        self.fail_delete = False

    async def create(self, snapshot: str, timeout: float) -> Sandbox:
        return self.sandbox

    async def delete(self, sandbox: Sandbox, timeout: float) -> None:
        self.delete_calls += 1
        self.deleting.set()
        await self.finish_delete.wait()
        if self.fail_delete:
            raise RuntimeError("delete failed")
        self.deleted = True


class Health:
    async def check(self, origin: str, path: str) -> bool:
        return True


def provider(runtime: Runtime, *, delete_timeout: float = 1) -> DaytonaSandboxProvider:
    target = RegisteredTarget(
        target_id="cartwheel-fixture",
        fixture_id="baseline",
        fixture_checksum="c" * 64,
        fixture_state_digest=hashlib.sha256(FIXTURE).hexdigest(),
        fixture_state_path="/workspace/fixture.json",
        repo_path="/workspace/repo",
        preview_port=3100,
        preview_domain_suffix=".proxy.daytona.work",
        ready_path="/ready",
        startup_profile="cartwheel_next_v1",
        snapshots=(RegisteredSnapshot(SHA, "fixture-snapshot", "d" * 64),),
    )
    return DaytonaSandboxProvider(
        runtime,
        {"cartwheel-fixture": target},
        Health(),
        delete_timeout=delete_timeout,
    )


def create(adapter: DaytonaSandboxProvider) -> asyncio.Task[object]:
    return asyncio.create_task(
        adapter.create(
            target_id="cartwheel-fixture",
            source_sha=SHA,
            fixture_id="baseline",
            mode="gate_compare",
        )
    )


def test_second_cancellation_during_delete_finishes_one_cleanup() -> None:
    async def scenario() -> None:
        runtime = Runtime()
        adapter = provider(runtime)
        task = create(adapter)
        await runtime.sandbox.verifying.wait()
        task.cancel()
        await runtime.deleting.wait()
        task.cancel()
        runtime.finish_delete.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert runtime.deleted
        assert runtime.delete_calls == 1
        assert adapter.pending_cleanup_ids == ()
        await adapter.destroy(runtime.sandbox.id)
        assert runtime.delete_calls == 1

    asyncio.run(scenario())


def test_second_cancellation_with_failed_delete_remains_retryable() -> None:
    async def scenario() -> None:
        runtime = Runtime()
        runtime.fail_delete = True
        adapter = provider(runtime)
        task = create(adapter)
        await runtime.sandbox.verifying.wait()
        task.cancel()
        await runtime.deleting.wait()
        task.cancel()
        runtime.finish_delete.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert adapter.pending_cleanup_ids == (runtime.sandbox.id,)
        assert runtime.delete_calls == 1
        runtime.fail_delete = False
        await adapter.destroy(runtime.sandbox.id)
        assert runtime.delete_calls == 2
        assert adapter.pending_cleanup_ids == ()

    asyncio.run(scenario())


def test_cleanup_wait_is_bounded_when_delete_stalls() -> None:
    async def scenario() -> None:
        runtime = Runtime()
        adapter = provider(runtime, delete_timeout=0.02)
        task = create(adapter)
        await runtime.sandbox.verifying.wait()
        task.cancel()
        await runtime.deleting.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 0.5)
        assert adapter.pending_cleanup_ids == (runtime.sandbox.id,)
        assert runtime.delete_calls == 1

    asyncio.run(scenario())


def test_retry_does_not_double_delete_while_timed_out_cleanup_is_running() -> None:
    class SlowCancellationRuntime(Runtime):
        async def delete(self, sandbox: Sandbox, timeout: float) -> None:
            self.delete_calls += 1
            self.deleting.set()
            try:
                await self.finish_delete.wait()
            except asyncio.CancelledError:
                await self.finish_delete.wait()
            self.deleted = True

    async def scenario() -> None:
        runtime = SlowCancellationRuntime()
        adapter = provider(runtime, delete_timeout=0.02)
        task = create(adapter)
        await runtime.sandbox.verifying.wait()
        task.cancel()
        await runtime.deleting.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 0.5)
        assert adapter.pending_cleanup_ids == (runtime.sandbox.id,)
        with pytest.raises(EnvironmentUnavailableError, match="still in progress"):
            await adapter.destroy(runtime.sandbox.id)
        assert runtime.delete_calls == 1
        runtime.finish_delete.set()
        await asyncio.wait_for(adapter.destroy(runtime.sandbox.id), 0.5)
        assert runtime.deleted
        assert runtime.delete_calls == 1
        assert adapter.pending_cleanup_ids == ()

    asyncio.run(scenario())


def test_cancelled_destroy_of_ready_sandbox_remains_retryable() -> None:
    class ReadySandbox(Sandbox):
        async def checkout_sha(self, repo_path: str) -> str:
            return SHA

    async def scenario() -> None:
        runtime = Runtime()
        runtime.sandbox = ReadySandbox()
        adapter = provider(runtime)
        environment = await adapter.create(
            target_id="cartwheel-fixture",
            source_sha=SHA,
            fixture_id="baseline",
            mode="gate_compare",
        )
        closing = asyncio.create_task(adapter.destroy(environment.environment_id))
        await runtime.deleting.wait()
        closing.cancel()
        with pytest.raises(asyncio.CancelledError):
            await closing
        assert adapter.pending_cleanup_ids == (environment.environment_id,)
        assert not await adapter.verify_fixture(environment.environment_id, "c" * 64)
        runtime.finish_delete.set()
        await adapter.destroy(environment.environment_id)
        assert runtime.delete_calls == 2
        assert runtime.deleted
        assert adapter.pending_cleanup_ids == ()

    asyncio.run(scenario())
