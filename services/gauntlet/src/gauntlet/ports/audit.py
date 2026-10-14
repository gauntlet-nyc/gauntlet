"""Authoritative-state evidence for one recorded tool operation (B implements per target)."""

from dataclasses import dataclass
from typing import Protocol

from gauntlet.contracts import ToolEvent


@dataclass(frozen=True)
class AuditFacts:
    """Facts established from authoritative records (ledger, order owner at event time).

    `forbidden_effect_confirmed` means the forbidden *result* happened (e.g. money moved to a
    non-owner), not merely that the caller and owner differed.
    """

    relevant_logs_complete: bool
    authoritative_state_checked: bool
    forbidden_effect_confirmed: bool
    rationale: str
    evidence_ids: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


class AuditEvidenceProvider(Protocol):
    criterion_version: str

    async def facts_for(self, event: ToolEvent) -> AuditFacts: ...
