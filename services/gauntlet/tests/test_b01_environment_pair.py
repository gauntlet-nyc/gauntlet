"""B-01: base/head environments share a checked fixture and cleanup scope."""

import asyncio
from dataclasses import replace

import pytest

from gauntlet.contracts import ChangeRequest
from gauntlet.execution.environment_pair import gate_environment_pair
from gauntlet.integrations.fake.sandbox import FakeSandboxProvider, Fixture
from gauntlet.ports.errors import EnvironmentUnavailableError
from gauntlet.ports.sandbox import EnvironmentHandle

BASE = "a" * 40
HEAD = "b" * 40
CHECKSUM = "c" * 64


def change() -> ChangeRequest:
    return ChangeRequest(
        repository_id="cartwheel",
        base_sha=BASE,
        head_sha=HEAD,
        fixture_id="baseline-v1",
        target_id="cartwheel-fixture",
        max_cost_usd_cents=500,
        feature_intent="Synthetic UI update",
    )


class RecordingSandbox(FakeSandboxProvider):
    def __init__(self) -> None:
        super().__init__(
            {"cartwheel-fixture": Fixture("baseline-v1", CHECKSUM, frozenset({BASE, HEAD}))}
        )
        self.created: list[EnvironmentHandle] = []
        self.fail_head = False
        self.wrong_head_checksum = False
        self.fail_verify_head = False
        self.drift_base_after_head = False

    async def create(self, **kwargs: object) -> EnvironmentHandle:
        if kwargs["source_sha"] == HEAD and self.fail_head:
            raise EnvironmentUnavailableError("head snapshot is unavailable")
        handle = await super().create(**kwargs)  # type: ignore[arg-type]
        self.created.append(handle)
        if kwargs["source_sha"] == HEAD and self.wrong_head_checksum:
            return replace(handle, fixture_checksum="d" * 64)
        return handle

    async def verify_fixture(self, environment_id: str, expected_checksum: str) -> bool:
        if self.drift_base_after_head and len(self.created) == 2:
            if environment_id == self.created[0].environment_id:
                return False
        if self.fail_verify_head and len(self.created) == 2:
            if environment_id == self.created[1].environment_id:
                return False
        return await super().verify_fixture(environment_id, expected_checksum)


def test_pair_yields_only_matching_verified_revisions_then_destroys_both() -> None:
    async def scenario() -> None:
        sandbox = RecordingSandbox()
        async with gate_environment_pair(sandbox, change(), CHECKSUM) as pair:
            assert pair.base.source_sha == BASE
            assert pair.head.source_sha == HEAD
            assert pair.base.environment_id != pair.head.environment_id
            assert await sandbox.verify_fixture(pair.base.environment_id, CHECKSUM)
            assert await sandbox.verify_fixture(pair.head.environment_id, CHECKSUM)
        assert all(
            [
                not await sandbox.verify_fixture(handle.environment_id, CHECKSUM)
                for handle in sandbox.created
            ]
        )

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["wrong_head_checksum", "fail_verify_head"])
def test_pair_never_yields_mismatched_or_unverified_head(failure: str) -> None:
    async def scenario() -> None:
        sandbox = RecordingSandbox()
        setattr(sandbox, failure, True)
        entered = False
        with pytest.raises(EnvironmentUnavailableError):
            async with gate_environment_pair(sandbox, change(), CHECKSUM):
                entered = True
        assert not entered
        assert len(sandbox.created) == 2
        assert all(
            [
                not await FakeSandboxProvider.verify_fixture(
                    sandbox, handle.environment_id, CHECKSUM
                )
                for handle in sandbox.created
            ]
        )

    asyncio.run(scenario())


def test_base_is_reverified_after_head_provisioning() -> None:
    async def scenario() -> None:
        sandbox = RecordingSandbox()
        sandbox.drift_base_after_head = True
        with pytest.raises(EnvironmentUnavailableError):
            async with gate_environment_pair(sandbox, change(), CHECKSUM):
                pytest.fail("drifted base was yielded")
        assert len(sandbox.created) == 2
        assert not await sandbox.verify_fixture(sandbox.created[1].environment_id, CHECKSUM)

    asyncio.run(scenario())


def test_head_creation_failure_releases_base() -> None:
    async def scenario() -> None:
        sandbox = RecordingSandbox()
        sandbox.fail_head = True
        with pytest.raises(EnvironmentUnavailableError):
            async with gate_environment_pair(sandbox, change(), CHECKSUM):
                pytest.fail("unready pair was yielded")
        assert len(sandbox.created) == 1
        assert not await sandbox.verify_fixture(sandbox.created[0].environment_id, CHECKSUM)

    asyncio.run(scenario())


def test_cancellation_releases_both_environments() -> None:
    async def scenario() -> None:
        sandbox = RecordingSandbox()
        entered = asyncio.Event()

        async def run() -> None:
            async with gate_environment_pair(sandbox, change(), CHECKSUM):
                entered.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(run())
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(sandbox.created) == 2
        assert all(
            [
                not await sandbox.verify_fixture(handle.environment_id, CHECKSUM)
                for handle in sandbox.created
            ]
        )

    asyncio.run(scenario())


def test_repeated_cancellation_during_cleanup_still_releases_both() -> None:
    class SlowDestroySandbox(RecordingSandbox):
        def __init__(self) -> None:
            super().__init__()
            self.destroy_started = asyncio.Event()
            self.release_destroy = asyncio.Event()
            self.first_destroy = True

        async def destroy(self, environment_id: str) -> None:
            if self.first_destroy:
                self.first_destroy = False
                self.destroy_started.set()
                await self.release_destroy.wait()
            await super().destroy(environment_id)

    async def scenario() -> None:
        sandbox = SlowDestroySandbox()
        entered = asyncio.Event()

        async def run() -> None:
            async with gate_environment_pair(sandbox, change(), CHECKSUM):
                entered.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(run())
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        await asyncio.wait_for(sandbox.destroy_started.wait(), 1)
        task.cancel()
        sandbox.release_destroy.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(sandbox.created) == 2
        assert all(
            [
                not await FakeSandboxProvider.verify_fixture(
                    sandbox, handle.environment_id, CHECKSUM
                )
                for handle in sandbox.created
            ]
        )

    asyncio.run(scenario())
