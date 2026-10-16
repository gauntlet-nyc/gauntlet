"""Typed, time-aware, provenance-backed memory facts (master plan Section 10.2).

`known_at` is when we learned it; `valid_from/valid_until` is when the behaviour held.
Corrections supersede older facts instead of overwriting them, so history stays inspectable.
"""

from typing import Literal, Self

from pydantic import Field, model_validator

from .common import GitSha, Identifier, OracleId, ShortText, StrictDTO, UtcDatetime
from .gate import SurfaceKind

MemoryKind = Literal[
    "ui_occlusion", "authz_bypass", "workflow_state", "policy_conflict", "fix_pattern"
]
MemoryTrust = Literal["verified_test", "policy", "app_content", "model_summary"]
MemoryLens = Literal["planner", "investigator", "fixer"]


class MemoryProvenance(StrictDTO):
    finding_id: Identifier | None = None
    oracle_id: OracleId | None = None
    commit: GitSha | None = None
    trace_id: Identifier | None = None


class TemporalMemoryFact(StrictDTO):
    fact_id: Identifier
    kind: MemoryKind
    summary: ShortText
    verification: Literal["confirmed", "unverified"]
    trust: MemoryTrust
    scope: str = Field(min_length=1, max_length=256, pattern=r"^[a-z0-9][a-z0-9_/.-]*$")
    surface_kinds: tuple[SurfaceKind, ...] = Field(min_length=1, max_length=6)
    source: MemoryProvenance
    known_at: UtcDatetime
    valid_from: UtcDatetime
    valid_until: UtcDatetime | None = None
    supersedes: Identifier | None = None

    @model_validator(mode="after")
    def provenance_and_time(self) -> Self:
        if self.valid_until is not None and self.valid_until <= self.valid_from:
            raise ValueError("valid_until must be after valid_from")
        if self.verification == "confirmed" and not (
            self.source.finding_id and self.source.oracle_id
        ):
            raise ValueError("a confirmed fact must cite the finding and oracle that proved it")
        if self.trust == "model_summary" and self.verification == "confirmed":
            raise ValueError("model summaries are never confirmed facts")
        if self.supersedes == self.fact_id:
            raise ValueError("a fact cannot supersede itself")
        return self
