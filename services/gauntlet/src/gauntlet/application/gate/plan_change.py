"""Gate step: change -> impact map -> validated plan -> frozen plan event, before any execution."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from gauntlet.contracts import ChangeImpactMap, ChangeRequest, RunEvent, SourceRef
from gauntlet.contracts.events import PayloadValue
from gauntlet.planning import (
    PLANNER_VERSION,
    AttackPlanner,
    FrozenPlan,
    SourceExcerpt,
    compute_plan_hash,
)
from gauntlet.ports import PortError, RepositoryInspector, RunStore

ACTOR: Final = "gate-planner"


@dataclass(frozen=True)
class PlanChangeDependencies:
    inspector: RepositoryInspector
    planner: AttackPlanner
    store: RunStore
    clock: Callable[[], datetime]
    new_event_id: Callable[[], str]
    max_excerpts: int = 12


class PlanChangeUseCase:
    def __init__(self, deps: PlanChangeDependencies) -> None:
        self._deps = deps

    async def execute(self, run_id: str, change: ChangeRequest) -> FrozenPlan:
        impact = await self._deps.inspector.inspect_change(change)
        await self._append(
            run_id,
            "impact_mapped",
            {
                "surfaces": len(impact.surfaces),
                "changed_files": len(impact.changed_files),
                "coverage_gaps": len(impact.coverage_gaps),
            },
        )
        excerpts, unreadable = await self._read_excerpts(change.repository_id, impact)
        draft = await self._deps.planner.plan(change, impact, excerpts)
        attacks = draft.validation.accepted
        frozen = FrozenPlan(
            run_id=run_id,
            plan_hash=compute_plan_hash(change, impact, attacks),
            planner_version=PLANNER_VERSION,
            frozen_at=self._deps.clock(),
            change=change,
            impact=impact,
            attacks=attacks,
            rejected=draft.validation.rejected,
            model_id=draft.model_id,
            not_tested_reason=draft.not_tested_reason,
        )
        await self._append(
            run_id,
            "plan_frozen",
            {
                "plan_hash": frozen.plan_hash,
                "planner_version": PLANNER_VERSION,
                "accepted_attacks": len(attacks),
                "rejected_attacks": len(frozen.rejected),
                "unreadable_excerpts": unreadable,
                "model_id": draft.model_id,
                "not_tested_reason": draft.not_tested_reason,
            },
            trace_id=draft.trace_id,
        )
        return frozen

    async def _read_excerpts(
        self, repository_id: str, impact: ChangeImpactMap
    ) -> tuple[list[SourceExcerpt], int]:
        refs: list[SourceRef] = []
        for surface in impact.surfaces:
            for ref in surface.source_refs:
                if ref not in refs:
                    refs.append(ref)
        excerpts: list[SourceExcerpt] = []
        unreadable = 0
        for ref in refs[: self._deps.max_excerpts]:
            try:
                text = await self._deps.inspector.read_source(repository_id, ref)
            except PortError:
                unreadable += 1
                continue
            excerpts.append(SourceExcerpt(ref=ref, text=text))
        return excerpts, unreadable

    async def _append(
        self,
        run_id: str,
        event_type: str,
        payload: dict[str, PayloadValue],
        trace_id: str | None = None,
    ) -> None:
        existing = await self._deps.store.list_events(run_id)
        sequence = existing[-1].sequence + 1 if existing else 0
        await self._deps.store.append_event(
            RunEvent(
                run_id=run_id,
                event_id=self._deps.new_event_id(),
                sequence=sequence,
                created_at=self._deps.clock(),
                actor=ACTOR,
                event_type=event_type,
                idempotency_key=f"{run_id}:{event_type}",
                payload=payload,
                trace_id=trace_id,
            )
        )
