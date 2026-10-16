"""Inbound webhooks: GitHub App pull_request events and ElevenLabs voice tool calls.

Nothing in a body is trusted until Session 2's verifiers check the HMAC and replay guard.
GitHub: only repositories in the server-side GAUNTLET_GITHUB_REPOSITORIES allowlist start a
run, and only when the PR's base/head are registered fixture revisions; anything else is
ignored or `not_tested`. The check run is published only with RUN_LIVE_INTEGRATIONS=1 and the
GitHub App keys; it is checks-only. ElevenLabs: read-only intents answer from stored findings;
a replay request is only opened pending operator confirmation on the dashboard/API.
"""

import logging
import uuid
from dataclasses import dataclass, field
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel

from gauntlet.application.voice import build_briefing, open_replay_request
from gauntlet.contracts import VoiceReplayRequest
from gauntlet.intake.github import EventIgnored, RepositoryBinding, render_check_run
from gauntlet.security.webhooks import (
    ElevenLabsWebhookVerifier,
    GitHubWebhookVerifier,
    WebhookRejectedError,
)
from gauntlet.settings import Settings

from ..container import get_container

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
log = logging.getLogger(__name__)


class WebhookAccepted(BaseModel):
    status: Literal["accepted", "ignored"]
    detail: str
    run_id: str | None = None


class VoiceAnswer(BaseModel):
    intent: str
    spoken_text: str
    replay_request: VoiceReplayRequest | None = None


@dataclass
class _WebhookState:
    github: GitHubWebhookVerifier | None = None
    voice: ElevenLabsWebhookVerifier | None = None
    replay_requests: dict[str, VoiceReplayRequest] = field(default_factory=dict)


_STATE = _WebhookState()


def _github_verifier() -> GitHubWebhookVerifier:
    if _STATE.github is None:
        core = Settings.from_env()
        secret = core.optional("GITHUB_WEBHOOK_SECRET")
        if secret is None:
            raise HTTPException(status_code=503, detail="missing GITHUB_WEBHOOK_SECRET")
        manifests = get_container().gate.manifests["help-button"]
        bindings = {
            repo: RepositoryBinding(
                repository_id="cartwheel",
                target_id=manifests["target_id"],
                fixture_id=manifests["fixture_id"],
                max_cost_usd_cents=500,
            )
            for repo in get_container().settings.github_repositories
        }
        _STATE.github = GitHubWebhookVerifier(secret.encode(), bindings)
    return _STATE.github


def _change_for(base_sha: str, head_sha: str) -> str | None:
    for change_id, refs in get_container().gate.manifests.items():
        if (refs["base_sha"], refs["head_sha"]) == (base_sha, head_sha):
            return change_id
    return None


async def _run_and_publish(repo: str, head_sha: str, change_id: str | None, delivery: str) -> None:
    container = get_container()
    if change_id is None:
        log.info("webhook %s: PR revisions are not registered fixture revisions", delivery)
        return
    view = await container.gate.start(change_id)
    core = Settings.from_env()
    if not core.run_live_integrations or container.settings.missing_env("github_app"):
        log.info(
            "webhook %s: run %s done; check run not published (not live)", delivery, view.run_id
        )
        return
    from gauntlet.integrations.github_app import GitHubAppCheckRunPublisher

    report = render_check_run(view.run_id, view.findings, [], view.not_tested_reason)
    publisher = GitHubAppCheckRunPublisher.from_settings(core.integrations())
    check_id = await publisher.publish(repo, head_sha, view.run_id, report)
    container.gate.append_event(view.run_id, "check_run_published", {"check_run_id": check_id})


@router.post("/github", status_code=202)
async def github_webhook(request: Request, background: BackgroundTasks) -> WebhookAccepted:
    verifier = _github_verifier()
    body = await request.body()
    try:
        result = verifier.handle(dict(request.headers), body)
    except WebhookRejectedError as exc:
        raise HTTPException(status_code=401, detail=exc.reason) from None
    if isinstance(result, EventIgnored):
        return WebhookAccepted(status="ignored", detail=result.reason)
    change_id = _change_for(result.change.base_sha, result.change.head_sha)
    delivery = request.headers.get("X-GitHub-Delivery", "")
    background.add_task(
        _run_and_publish, result.repository_full_name, result.head_sha, change_id, delivery
    )
    if change_id is None:
        return WebhookAccepted(
            status="ignored",
            detail="PR base/head are not registered fixture revisions; not tested",
        )
    return WebhookAccepted(status="accepted", detail=f"Gate run started for {change_id}")


def _voice_verifier() -> ElevenLabsWebhookVerifier:
    if _STATE.voice is None:
        core = Settings.from_env()
        secret = core.optional("VOICE_WEBHOOK_SECRET")
        agent = core.optional("ELEVENLABS_AGENT_ID")
        if secret is None or agent is None:
            raise HTTPException(
                status_code=503, detail="missing VOICE_WEBHOOK_SECRET or ELEVENLABS_AGENT_ID"
            )
        _STATE.voice = ElevenLabsWebhookVerifier(secret.encode(), agent_id=agent)
    return _STATE.voice


@router.post("/elevenlabs")
async def elevenlabs_webhook(request: Request) -> VoiceAnswer:
    """Voice can only read findings or ask for a replay; it can never approve anything."""
    verifier = _voice_verifier()
    body = await request.body()
    try:
        call = verifier.parse_tool_call(dict(request.headers), body)
    except WebhookRejectedError as exc:
        raise HTTPException(status_code=401, detail=exc.reason) from None
    runs = get_container().gate.runs
    record = runs.get(call.run_id or "")
    if call.intent == "replay_request":
        if record is None:
            return VoiceAnswer(intent=call.intent, spoken_text="I can't find that run.")
        pending = open_replay_request(call, f"voice-replay-{uuid.uuid4().hex[:12]}")
        _STATE.replay_requests[pending.request_id] = pending
        return VoiceAnswer(
            intent=call.intent,
            spoken_text="Replay requested. An operator must confirm it on the dashboard.",
            replay_request=pending,
        )
    if record is None and call.intent != "finding_explanation":
        return VoiceAnswer(intent=call.intent, spoken_text="I can't find that run.")
    if call.intent == "finding_explanation":
        for run in runs.values():
            for finding in run.view.findings:
                if finding.finding_id == call.finding_id:
                    text = (
                        f"{finding.finding_id}: {finding.status.value.replace('_', ' ')}, "
                        f"head {finding.head_reproductions} of {finding.head_attempts}, "
                        f"base {finding.base_reproductions} of {finding.base_attempts}."
                    )
                    return VoiceAnswer(intent=call.intent, spoken_text=text)
        return VoiceAnswer(intent=call.intent, spoken_text="I can't find that finding.")
    assert record is not None
    view = record.view
    gaps = 1 if view.status == "not_tested" else 0
    briefing = build_briefing(
        view.run_id, view.findings, gaps, view.events[-1].sequence if view.events else 0
    )
    if call.intent == "inconclusive_list":
        open_items = [f.finding_id for f in view.findings if f.status.value != "passed"]
        text = (
            "Not passed: " + (", ".join(open_items) or "none") + ". Not tested does not mean safe."
        )
        return VoiceAnswer(intent=call.intent, spoken_text=text)
    return VoiceAnswer(intent=call.intent, spoken_text=briefing.spoken_summary)
