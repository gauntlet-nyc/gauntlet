"""Immutable evidence binding (issue #22): which trusted collector produced which bytes, for
which run/attempt/observation/step, on which code and fixture.

The hash is computed by the store from the bytes it received, never taken from the caller.
A binding cannot be rewritten or moved to another attempt. Page text and planner output can
never establish provenance; only a registered collector can.
"""

from typing import Final, Literal, Self

from pydantic import Field, model_validator

from .common import EvidenceRef, GitSha, Identifier, Sha256Hex, StrictDTO, UtcDatetime

EVIDENCE_MEDIA_TYPES: Final = frozenset(
    {"image/png", "image/jpeg", "video/webm", "video/mp4", "application/json", "text/plain"}
)
MAX_EVIDENCE_BYTES: Final = 50 * 1024 * 1024

EvidenceCollector = Literal["browser_collector", "api_collector", "replay_collector"]


class EvidenceSubject(StrictDTO):
    """What the evidence is about. Supplied by the trusted collector at capture time."""

    run_id: Identifier
    attempt_id: Identifier
    observation_id: Identifier
    environment_id: Identifier
    source_sha: GitSha
    fixture_checksum: Sha256Hex
    step_index: int | None = Field(default=None, ge=0)
    collector: EvidenceCollector


class EvidenceBinding(StrictDTO):
    """Written once by the artifact store; the verifier re-checks it against stored bytes."""

    evidence: EvidenceRef
    subject: EvidenceSubject
    byte_size: int = Field(ge=1, le=MAX_EVIDENCE_BYTES)
    recorded_at: UtcDatetime

    @model_validator(mode="after")
    def media_and_time(self) -> Self:
        if self.evidence.media_type not in EVIDENCE_MEDIA_TYPES:
            raise ValueError("evidence media type is not allowed")
        if self.recorded_at < self.evidence.created_at:
            raise ValueError("recorded_at cannot precede created_at")
        return self
