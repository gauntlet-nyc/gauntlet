"""Which remembered facts may influence a plan. Re-applied here even if the store filtered.

Only confirmed, provenance-backed facts from trusted sources; only what was known *and*
valid at `as_of` (no hindsight in historical benchmarks); superseded facts are hidden from
planning but remain in the store for audit.
"""

from collections.abc import Iterable
from datetime import datetime
from typing import Final

from gauntlet.contracts import SurfaceKind, TemporalMemoryFact

PLANNING_TRUST: Final = frozenset({"verified_test", "policy"})


def select_memory(
    facts: Iterable[TemporalMemoryFact],
    as_of: datetime,
    surface_kinds: frozenset[SurfaceKind],
    limit: int,
) -> tuple[TemporalMemoryFact, ...]:
    visible = [
        f
        for f in facts
        if f.verification == "confirmed"
        and f.trust in PLANNING_TRUST
        and f.known_at <= as_of
        and f.valid_from <= as_of
        and (f.valid_until is None or as_of < f.valid_until)
        and surface_kinds.intersection(f.surface_kinds)
    ]
    superseded = {f.supersedes for f in visible if f.supersedes}
    current = [f for f in visible if f.fact_id not in superseded]
    current.sort(key=lambda f: (f.known_at, f.fact_id), reverse=True)
    return tuple(current[:limit])
