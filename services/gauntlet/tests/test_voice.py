"""A-08: voice can read sanitized results and request a re-test; it can never approve,
merge, deploy, refund or confirm its own request."""

import json
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from gauntlet.application.gate import AuthenticatedReviewer
from gauntlet.application.voice import (
    REPLAY_REQUEST_TTL,
    VoiceRequestError,
    build_briefing,
    decide_replay_request,
    open_replay_request,
)
from gauntlet.contracts import Finding, VoiceReplayRequest, VoiceToolCall

EXAMPLES = Path(__file__).resolve().parents[3] / "docs" / "contracts" / "examples"
OPERATOR = AuthenticatedReviewer(reviewer_id="reviewer-rudra", channel="dashboard")


def load(name: str) -> dict[str, object]:
    data: dict[str, object] = json.loads((EXAMPLES / name).read_text(encoding="utf-8"))
    return data


CALL = VoiceToolCall.model_validate(load("voice-tool-call.v1.json"))
REGRESSION = Finding.model_validate(load("finding.v1.json"))


@pytest.mark.parametrize("intent", ["approve_fix", "merge", "deploy", "issue_refund", "remediate"])
def test_dangerous_intents_are_not_representable(intent: str) -> None:
    with pytest.raises(ValidationError):
        VoiceToolCall.model_validate({**load("voice-tool-call.v1.json"), "intent": intent})


def test_intents_need_their_references() -> None:
    with pytest.raises(ValidationError):
        VoiceToolCall.model_validate({**load("voice-tool-call.v1.json"), "attack_id": None})
    with pytest.raises(ValidationError):
        VoiceToolCall.model_validate(
            {**load("voice-tool-call.v1.json"), "intent": "finding_explanation"}
        )


def test_replay_request_waits_for_an_operator() -> None:
    request = open_replay_request(CALL, "replay-req-001")
    assert request.status == "pending_operator_confirmation"
    assert request.confirmed_by is None
    assert request.expires_at - request.requested_at == REPLAY_REQUEST_TTL


def test_operator_confirms_on_a_non_voice_channel() -> None:
    request = open_replay_request(CALL, "replay-req-001")
    confirmed = decide_replay_request(request, OPERATOR, True, CALL.received_at)
    assert confirmed.status == "confirmed"
    assert (confirmed.confirmed_by, confirmed.confirmed_channel) == ("reviewer-rudra", "dashboard")
    declined = decide_replay_request(request, OPERATOR, False, CALL.received_at)
    assert declined.status == "declined"


def test_expired_request_cannot_be_confirmed_and_decisions_are_final() -> None:
    request = open_replay_request(CALL, "replay-req-001")
    late = CALL.received_at + REPLAY_REQUEST_TTL + timedelta(seconds=1)
    assert decide_replay_request(request, OPERATOR, True, late).status == "expired"
    confirmed = decide_replay_request(request, OPERATOR, True, CALL.received_at)
    with pytest.raises(VoiceRequestError):
        decide_replay_request(confirmed, OPERATOR, False, CALL.received_at)


def test_voice_channel_cannot_confirm_by_construction() -> None:
    with pytest.raises(ValidationError):
        VoiceReplayRequest.model_validate(
            {**load("voice-replay-request.v1.json"), "status": "confirmed",
             "confirmed_by": "caller", "confirmed_channel": "voice"}
        )  # fmt: skip
    with pytest.raises(ValidationError):
        VoiceReplayRequest.model_validate(
            {**load("voice-replay-request.v1.json"), "status": "confirmed"}
        )


def test_only_replay_calls_open_requests() -> None:
    summary_call = VoiceToolCall.model_validate(
        {**load("voice-tool-call.v1.json"), "intent": "run_summary"}
    )
    with pytest.raises(VoiceRequestError):
        open_replay_request(summary_call, "x")


def test_briefing_counts_come_from_findings_and_never_imply_safety() -> None:
    suspected = Finding.model_validate(
        {**load("finding.v1.json"), "finding_id": "finding-002", "status": "suspected",
         "attribution": "unknown", "severity": "low"}
    )  # fmt: skip
    briefing = build_briefing("run-001", [suspected, REGRESSION], coverage_gaps=2,
                              source_event_sequence=9)  # fmt: skip
    assert (briefing.confirmed, briefing.suspected, briefing.not_tested) == (1, 1, 0)
    assert briefing.findings[0].finding_id == "finding-001", "most severe first"
    assert "Most serious: high confirmed regression on attack-ui-001" in briefing.spoken_summary
    assert "Not tested does not mean safe." in briefing.spoken_summary


def test_empty_run_briefing_is_honest() -> None:
    briefing = build_briefing("run-009", [], coverage_gaps=0, source_event_sequence=1)
    assert briefing.spoken_summary == (
        "Run run-009: 0 confirmed, 0 suspected, 0 not tested, 0 coverage gaps."
    )
