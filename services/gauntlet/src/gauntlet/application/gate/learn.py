"""P7: turn confirmed Gate findings into verified, provenance-backed memory facts.

Only confirmed hard-oracle findings are remembered, each citing its finding, oracle and head
commit. Nothing unconfirmed or model-written becomes a planning fact. Memory is append-only;
planners later read it as of a point in time, so a historical replay never sees the future.
"""

from collections.abc import Callable
from datetime import datetime
from typing import Final

from gauntlet.contracts import (
    AttackSpec,
    ChangeImpactMap,
    Finding,
    MemoryKind,
    MemoryProvenance,
    SurfaceKind,
    TemporalMemoryFact,
    WorkerKind,
)
from gauntlet.domain import CONFIRMED_GATE_STATUSES
from gauntlet.planning.worker_selector import WORKERS_BY_SURFACE
from gauntlet.ports import MemoryWriter

from .run_gate import GateRunReport

_KIND: Final[dict[WorkerKind, MemoryKind]] = {
    "ui": "ui_occlusion",
    "accessibility": "ui_occlusion",
    "ai_agent": "authz_bypass",
    "api": "authz_bypass",
    "workflow": "workflow_state",
    "concurrency": "workflow_state",
}


def _surfaces(attack: AttackSpec, impact: ChangeImpactMap) -> tuple[SurfaceKind, ...]:
    """Changed surface kinds this worker covers: where the lesson applies next time."""
    kinds = [s.kind for s in impact.surfaces if attack.worker_kind in WORKERS_BY_SURFACE[s.kind]]
    return tuple(dict.fromkeys(kinds))


def fact_for(
    finding: Finding,
    attack: AttackSpec,
    impact: ChangeImpactMap,
    *,
    target_id: str,
    head_sha: str,
    known_at: datetime,
) -> TemporalMemoryFact | None:
    surfaces = _surfaces(attack, impact)
    if finding.status not in CONFIRMED_GATE_STATUSES or not surfaces:
        return None
    steps = ", ".join(step.action for step in attack.steps)
    return TemporalMemoryFact(
        fact_id=f"fact-{finding.finding_id}-{head_sha[:12]}",
        kind=_KIND[attack.worker_kind],
        summary=(
            f"Verified {finding.status.value}: {attack.hypothesis} "
            f"(head {finding.head_reproductions}/{finding.head_attempts}, base "
            f"{finding.base_reproductions}/{finding.base_attempts}; steps: {steps})"
        )[:2500],
        verification="confirmed",
        trust="verified_test",
        scope=f"project/{target_id}",
        surface_kinds=surfaces[:6],
        source=MemoryProvenance(
            finding_id=finding.finding_id, oracle_id=finding.oracle_ids[0], commit=head_sha
        ),
        known_at=known_at,
        valid_from=known_at,
    )


class LearnFromGateUseCase:
    def __init__(self, writer: MemoryWriter, clock: Callable[[], datetime]) -> None:
        self._writer = writer
        self._clock = clock

    async def remember(self, report: GateRunReport) -> tuple[TemporalMemoryFact, ...]:
        now = self._clock()
        facts: list[TemporalMemoryFact] = []
        for outcome in report.outcomes:
            fact = fact_for(
                outcome.finding,
                outcome.attack,
                report.plan.impact,
                target_id=report.plan.change.target_id,
                head_sha=report.plan.change.head_sha,
                known_at=now,
            )
            if fact is not None:
                await self._writer.remember(fact)
                facts.append(fact)
        return tuple(facts)
