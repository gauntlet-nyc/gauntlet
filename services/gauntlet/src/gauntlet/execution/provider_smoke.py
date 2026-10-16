"""Fixed, provider-independent browser capture for B-01 live smoke only.

This checks resource creation, the synthetic compiled-build receipt, scoped
navigation, screenshot storage and cleanup. It does not attest the sandbox
image or prove a Gate finding.
"""

import asyncio
import hashlib
from dataclasses import dataclass
from uuid import uuid4

import httpx

from gauntlet.application.image_format import valid_screenshot
from gauntlet.contracts import CaptureStep, ChangeRequest, EvidenceSubject, NavigateStep
from gauntlet.integrations.daytona.provider import RegisteredTarget
from gauntlet.integrations.fixture_identity import verify_hosted_fixture_build_receipt
from gauntlet.ports.artifacts import ArtifactStore
from gauntlet.ports.browser import BrowserProvider
from gauntlet.ports.errors import EnvironmentUnavailableError
from gauntlet.ports.sandbox import EnvironmentHandle, SandboxProvider

from .environment_pair import gate_environment_pair


@dataclass(frozen=True)
class ProviderSmokeCapture:
    environment_id: str
    source_sha: str
    artifact_id: str
    sha256: str
    # Provider session facts (Anchor recording ID, egress isolation) when the adapter has them.
    browser_session: dict[str, str | bool | None] | None = None


async def _close_session(browser: BrowserProvider, session_id: str) -> None:
    cleanup = asyncio.create_task(browser.close_session(session_id))
    cancelled = False
    while not cleanup.done():
        try:
            await asyncio.shield(cleanup)
        except asyncio.CancelledError:
            cancelled = True
    cleanup.result()
    if cancelled:
        raise asyncio.CancelledError


async def _capture_one(
    browser: BrowserProvider,
    artifacts: ArtifactStore,
    environment: EnvironmentHandle,
    *,
    run_id: str,
    path: NavigateStep,
) -> ProviderSmokeCapture:
    subject = EvidenceSubject(
        run_id=run_id,
        attempt_id=f"smoke-attempt-{uuid4().hex}",
        observation_id=f"smoke-observation-{uuid4().hex}",
        environment_id=environment.environment_id,
        source_sha=environment.source_sha,
        fixture_checksum=environment.fixture_checksum,
        collector="browser_collector",
    )
    session_id = await browser.open_session(environment, subject)
    try:
        navigation = await browser.perform(session_id, 0, path)
        if (
            navigation.step_index != 0
            or navigation.action != "navigate"
            or navigation.outcome != "ok"
        ):
            raise EnvironmentUnavailableError("provider smoke navigation failed")
        capture = await browser.perform(session_id, 1, CaptureStep(label="provider-smoke"))
        if (
            capture.step_index != 1
            or capture.action != "capture"
            or capture.outcome != "ok"
            or len(capture.evidence_ids) != 1
        ):
            raise EnvironmentUnavailableError("provider smoke screenshot failed")
        artifact_id = capture.evidence_ids[0]
        stored = await artifacts.get(artifact_id)
        if (
            stored is None
            or stored.binding.evidence.artifact_id != artifact_id
            or stored.binding.subject != subject.model_copy(update={"step_index": 1})
            or not valid_screenshot(stored.content, stored.binding.evidence.media_type)
            or len(stored.content) != stored.binding.byte_size
            or hashlib.sha256(stored.content).hexdigest() != stored.binding.evidence.sha256
        ):
            raise EnvironmentUnavailableError("provider smoke evidence is missing or invalid")
        describe = getattr(browser, "session_evidence", None)
        session_facts = describe(session_id).as_payload() if callable(describe) else None
        return ProviderSmokeCapture(
            environment_id=environment.environment_id,
            source_sha=environment.source_sha,
            artifact_id=artifact_id,
            sha256=stored.binding.evidence.sha256,
            browser_session=session_facts,
        )
    finally:
        await _close_session(browser, session_id)


async def capture_provider_pair(
    sandbox: SandboxProvider,
    browser: BrowserProvider,
    artifacts: ArtifactStore,
    change: ChangeRequest,
    expected_checksum: str,
    *,
    ready_path: str,
    registered_target: RegisteredTarget | None = None,
    receipt_transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[ProviderSmokeCapture, ProviderSmokeCapture]:
    """Capture verified revisions after checking each registered hosted build."""
    if registered_target is None:
        raise EnvironmentUnavailableError("provider smoke requires target registration")
    if registered_target is not None and (
        registered_target.target_id != change.target_id
        or registered_target.fixture_id != change.fixture_id
        or registered_target.fixture_checksum != expected_checksum
        or {snapshot.source_sha for snapshot in registered_target.snapshots}
        != {change.base_sha, change.head_sha}
    ):
        raise EnvironmentUnavailableError("provider smoke target registration does not match")
    navigation = NavigateStep(path=ready_path)
    run_id = f"provider-smoke-{uuid4().hex}"
    async with gate_environment_pair(sandbox, change, expected_checksum) as pair:
        if registered_target is not None:
            await verify_hosted_fixture_build_receipt(
                pair.base.preview_origin,
                pair.base.source_sha,
                preview_domain_suffix=registered_target.preview_domain_suffix,
                transport=receipt_transport,
            )
        base = await _capture_one(browser, artifacts, pair.base, run_id=run_id, path=navigation)
        if registered_target is not None:
            await verify_hosted_fixture_build_receipt(
                pair.head.preview_origin,
                pair.head.source_sha,
                preview_domain_suffix=registered_target.preview_domain_suffix,
                transport=receipt_transport,
            )
        head = await _capture_one(browser, artifacts, pair.head, run_id=run_id, path=navigation)
    return base, head
