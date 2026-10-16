"""Voice (ElevenLabs) tool contracts. Voice can read sanitized results and *request* a re-test.

Approve, merge, deploy, refund and remediation are not representable intents. A replay
request stays pending until an authenticated operator confirms it on the dashboard or API.
"""

from typing import Literal, Self

from pydantic import Field, model_validator

from gauntlet.domain import GateStatus, Severity

from .approvals import ApprovalChannel
from .common import Identifier, ShortText, StrictDTO, UtcDatetime

VoiceIntent = Literal["run_summary", "finding_explanation", "inconclusive_list", "replay_request"]


class VoiceToolCall(StrictDTO):
    """A webhook call whose signature the API already verified; `caller_ref` comes from that."""

    call_id: Identifier
    intent: VoiceIntent
    caller_ref: Identifier
    run_id: Identifier | None = None
    finding_id: Identifier | None = None
    attack_id: Identifier | None = None
    received_at: UtcDatetime

    @model_validator(mode="after")
    def references_fit_intent(self) -> Self:
        if self.intent == "finding_explanation" and not self.finding_id:
            raise ValueError("finding_explanation needs finding_id")
        if self.intent == "replay_request" and not (self.run_id and self.attack_id):
            raise ValueError("replay_request needs run_id and attack_id")
        if self.intent in ("run_summary", "inconclusive_list") and not self.run_id:
            raise ValueError(f"{self.intent} needs run_id")
        return self


class BriefFinding(StrictDTO):
    finding_id: Identifier
    status: GateStatus
    severity: Severity
    headline: ShortText


class VoiceBriefing(StrictDTO):
    """Built only from persisted findings; `source_event_sequence` ties it to the event log."""

    run_id: Identifier
    source_event_sequence: int = Field(ge=0)
    findings: tuple[BriefFinding, ...] = Field(max_length=20)
    confirmed: int = Field(ge=0)
    suspected: int = Field(ge=0)
    not_tested: int = Field(ge=0)
    coverage_gaps: int = Field(ge=0)
    spoken_summary: ShortText


class VoiceReplayRequest(StrictDTO):
    request_id: Identifier
    run_id: Identifier
    attack_id: Identifier
    requested_by: Identifier
    requested_at: UtcDatetime
    expires_at: UtcDatetime
    status: Literal["pending_operator_confirmation", "confirmed", "declined", "expired"]
    confirmed_by: Identifier | None = None
    confirmed_channel: ApprovalChannel | None = None

    @model_validator(mode="after")
    def confirmation_is_human_and_not_voice(self) -> Self:
        if self.expires_at <= self.requested_at:
            raise ValueError("expires_at must be after requested_at")
        decided = self.status in ("confirmed", "declined")
        has_operator = self.confirmed_by is not None and self.confirmed_channel is not None
        if decided != has_operator:
            raise ValueError("confirmed/declined requires an operator and a non-voice channel")
        return self
