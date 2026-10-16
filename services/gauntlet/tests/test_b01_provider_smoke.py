"""B-01 provider smoke: fixed navigation, bound screenshot and scoped cleanup."""

import asyncio
import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from gauntlet.contracts import ActionRecord, ChangeRequest, EvidenceSubject
from gauntlet.execution.provider_smoke import capture_provider_pair
from gauntlet.integrations.daytona.provider import RegisteredSnapshot, RegisteredTarget
from gauntlet.integrations.fake.sandbox import FakeSandboxProvider, Fixture
from gauntlet.integrations.local_artifacts import LocalArtifactStore
from gauntlet.ports.browser import is_browser_subject_for
from gauntlet.ports.errors import EnvironmentUnavailableError
from gauntlet.ports.sandbox import EnvironmentHandle

BASE = "a" * 40
HEAD = "b" * 40
CHECKSUM = "c" * 64
PNG = b"\x89PNG\r\n\x1a\nsynthetic-smoke-image"


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

    async def create(self, **kwargs: object) -> EnvironmentHandle:
        handle = await super().create(**kwargs)  # type: ignore[arg-type]
        label = "base" if handle.source_sha == BASE else "head"
        handle = replace(handle, preview_origin=f"https://signed-{label}.proxy.daytona.work")
        self._active[handle.environment_id] = handle
        self.created.append(handle)
        return handle


def target() -> RegisteredTarget:
    return RegisteredTarget(
        target_id="cartwheel-fixture",
        fixture_id="baseline-v1",
        fixture_checksum=CHECKSUM,
        fixture_state_digest="d" * 64,
        fixture_state_path="/fixtures/state.json",
        repo_path="/workspace/cartwheel",
        preview_port=3000,
        preview_domain_suffix=".proxy.daytona.work",
        ready_path="/checkout",
        startup_profile="cartwheel_next_v1",
        snapshots=(
            RegisteredSnapshot(BASE, "base-snapshot", "e" * 64),
            RegisteredSnapshot(HEAD, "head-snapshot", "e" * 64),
        ),
    )


def receipt_transport() -> httpx.MockTransport:
    def respond(request: httpx.Request) -> httpx.Response:
        sha = BASE if request.url.host.startswith("signed-base.") else HEAD
        return httpx.Response(
            200,
            stream=httpx.ByteStream(
                json.dumps({"schema_version": "1.0", "source_sha": sha}).encode()
            ),
            headers={"content-type": "application/json"},
        )

    return httpx.MockTransport(respond)


class RecordingBrowser:
    def __init__(self, store: LocalArtifactStore) -> None:
        self.store = store
        self.sessions: dict[str, tuple[EnvironmentHandle, EvidenceSubject]] = {}
        self.opened: list[str] = []
        self.navigated: list[str] = []
        self.fail_head_navigation = False
        self.corrupt_capture = False

    async def open_session(self, environment: EnvironmentHandle, subject: EvidenceSubject) -> str:
        assert is_browser_subject_for(environment, subject)
        session_id = f"session-{len(self.opened)}"
        self.sessions[session_id] = (environment, subject)
        self.opened.append(session_id)
        return session_id

    async def perform(self, session_id: str, step_index: int, step: object) -> ActionRecord:
        environment, subject = self.sessions[session_id]
        if step_index == 0:
            assert step.action == "navigate" and step.path == "/checkout"  # type: ignore[attr-defined]
            self.navigated.append(environment.source_sha)
            outcome = (
                "blocked" if self.fail_head_navigation and environment.source_sha == HEAD else "ok"
            )
            return ActionRecord(step_index=0, action="navigate", outcome=outcome)
        assert step_index == 1 and step.action == "capture"  # type: ignore[attr-defined]
        binding = await self.store.put(
            b"not a png" if self.corrupt_capture else PNG,
            "image/png",
            subject.model_copy(update={"step_index": 1}),
        )
        return ActionRecord(
            step_index=1,
            action="capture",
            outcome="ok",
            evidence_ids=(binding.evidence.artifact_id,),
        )

    async def close_session(self, session_id: str) -> None:
        self.sessions.pop(session_id)


def test_pair_smoke_captures_bound_png_for_each_revision(tmp_path: Path) -> None:
    async def scenario() -> None:
        sandbox = RecordingSandbox()
        store = LocalArtifactStore(tmp_path)
        browser = RecordingBrowser(store)
        captures = await capture_provider_pair(
            sandbox,
            browser,
            store,
            change(),
            CHECKSUM,
            ready_path="/checkout",
            registered_target=target(),
            receipt_transport=receipt_transport(),
        )
        assert [item.source_sha for item in captures] == [BASE, HEAD]
        assert browser.navigated == [BASE, HEAD]
        assert len({item.artifact_id for item in captures}) == 2
        for capture in captures:
            stored = await store.get(capture.artifact_id)
            assert stored is not None and stored.content == PNG
            assert stored.binding.evidence.sha256 == capture.sha256
        assert browser.sessions == {}
        assert all(
            [
                not await FakeSandboxProvider.verify_fixture(sandbox, env.environment_id, CHECKSUM)
                for env in sandbox.created
            ]
        )

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["fail_head_navigation", "corrupt_capture"])
def test_smoke_rejects_failed_action_or_invalid_screenshot_and_cleans_up(
    tmp_path: Path, failure: str
) -> None:
    async def scenario() -> None:
        sandbox = RecordingSandbox()
        store = LocalArtifactStore(tmp_path)
        browser = RecordingBrowser(store)
        setattr(browser, failure, True)
        with pytest.raises(EnvironmentUnavailableError):
            await capture_provider_pair(
                sandbox,
                browser,
                store,
                change(),
                CHECKSUM,
                ready_path="/checkout",
                registered_target=target(),
                receipt_transport=receipt_transport(),
            )
        assert browser.sessions == {}
        assert len(sandbox.created) == 2
        assert all(
            [
                not await FakeSandboxProvider.verify_fixture(sandbox, env.environment_id, CHECKSUM)
                for env in sandbox.created
            ]
        )

    asyncio.run(scenario())


def test_repeated_cancel_during_browser_close_still_cleans_up(tmp_path: Path) -> None:
    class SlowCloseBrowser(RecordingBrowser):
        def __init__(self, store: LocalArtifactStore) -> None:
            super().__init__(store)
            self.close_started = asyncio.Event()
            self.release_close = asyncio.Event()

        async def close_session(self, session_id: str) -> None:
            self.close_started.set()
            await self.release_close.wait()
            await super().close_session(session_id)

    async def scenario() -> None:
        sandbox = RecordingSandbox()
        store = LocalArtifactStore(tmp_path)
        browser = SlowCloseBrowser(store)
        task = asyncio.create_task(
            capture_provider_pair(
                sandbox,
                browser,
                store,
                change(),
                CHECKSUM,
                ready_path="/checkout",
                registered_target=target(),
                receipt_transport=receipt_transport(),
            )
        )
        await asyncio.wait_for(browser.close_started.wait(), 1)
        task.cancel()
        browser.release_close.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert browser.sessions == {}
        assert all(
            [
                not await FakeSandboxProvider.verify_fixture(sandbox, env.environment_id, CHECKSUM)
                for env in sandbox.created
            ]
        )

    asyncio.run(scenario())
