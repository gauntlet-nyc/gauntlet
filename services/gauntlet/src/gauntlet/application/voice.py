"""Voice-safe actions. Briefings are templated from persisted findings (no model, no free
text from the caller); replay requests wait for a human on a non-voice channel."""

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Final

from gauntlet.contracts import (
    BriefFinding,
    Finding,
    VoiceBriefing,
    VoiceReplayRequest,
    VoiceToolCall,
)
from gauntlet.domain import CONFIRMED_GATE_STATUSES, GateStatus, Severity

from .errors import ApplicationError
from .gate.approvals import AuthenticatedReviewer

REPLAY_REQUEST_TTL: Final = timedelta(minutes=15)
_SEVERITY_ORDER: Final = {s: i for i, s in enumerate(Severity)}
_MAX_SPOKEN_FINDINGS: Final = 20


class VoiceRequestError(ApplicationError):
    """A voice call or confirmation is not valid for the request's current state."""


def _headline(finding: Finding) -> str:
    return f"{str(finding.status).replace('_', ' ')} on {finding.attack_id}"


def build_briefing(
    run_id: str,
    findings: Sequence[Finding],
    coverage_gaps: int,
    source_event_sequence: int,
) -> VoiceBriefing:
    ordered = sorted(findings, key=lambda f: (_SEVERITY_ORDER[f.severity], f.finding_id))
    confirmed = sum(f.status in CONFIRMED_GATE_STATUSES for f in findings)
    suspected = sum(f.status is GateStatus.SUSPECTED for f in findings)
    not_tested = sum(f.status is GateStatus.NOT_TESTED for f in findings)
    serious = next((f for f in ordered if f.status in CONFIRMED_GATE_STATUSES), None)
    summary = (
        f"Run {run_id}: {confirmed} confirmed, {suspected} suspected, {not_tested} not tested, "
        f"{coverage_gaps} coverage gaps."
    )
    if serious is not None:
        summary += f" Most serious: {serious.severity} {_headline(serious)}."
    if not_tested or coverage_gaps:
        summary += " Not tested does not mean safe."
    return VoiceBriefing(
        run_id=run_id,
        source_event_sequence=source_event_sequence,
        findings=tuple(
            BriefFinding(
                finding_id=f.finding_id,
                status=f.status,
                severity=f.severity,
                headline=_headline(f),
            )  # fmt: skip
            for f in ordered[:_MAX_SPOKEN_FINDINGS]
        ),
        confirmed=confirmed,
        suspected=suspected,
        not_tested=not_tested,
        coverage_gaps=coverage_gaps,
        spoken_summary=summary,
    )


def open_replay_request(call: VoiceToolCall, request_id: str) -> VoiceReplayRequest:
    if call.intent != "replay_request" or call.run_id is None or call.attack_id is None:
        raise VoiceRequestError("only a replay_request call can open a replay request")
    return VoiceReplayRequest(
        request_id=request_id,
        run_id=call.run_id,
        attack_id=call.attack_id,
        requested_by=call.caller_ref,
        requested_at=call.received_at,
        expires_at=call.received_at + REPLAY_REQUEST_TTL,
        status="pending_operator_confirmation",
    )


def decide_replay_request(
    request: VoiceReplayRequest,
    operator: AuthenticatedReviewer,
    accept: bool,
    now: datetime,
) -> VoiceReplayRequest:
    """An authenticated operator on the dashboard/API confirms or declines. Voice cannot."""
    if request.status != "pending_operator_confirmation":
        raise VoiceRequestError(f"request is already {request.status}")
    if now >= request.expires_at:
        return request.model_copy(update={"status": "expired"})
    return VoiceReplayRequest.model_validate(
        {
            **request.model_dump(),
            "status": "confirmed" if accept else "declined",
            "confirmed_by": operator.reviewer_id,
            "confirmed_channel": operator.channel,
        }
    )


__all__ = [
    "REPLAY_REQUEST_TTL",
    "VoiceRequestError",
    "build_briefing",
    "decide_replay_request",
    "open_replay_request",
]
