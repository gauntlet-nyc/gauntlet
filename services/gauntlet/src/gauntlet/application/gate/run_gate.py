"""Gate use case: ChangeRequest -> frozen plan -> base/head sandboxes -> attempts -> Findings.

Order is fixed: the plan is frozen (hashed and recorded) before any environment exists.
Every attack runs unchanged on head and on base, ``attempts_per_side`` times each, in
environments whose fixture checksum is verified. Only the pure adjudicator assigns a status.
Nothing here merges, deploys or remediates.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

from gauntlet.contracts import (
    AttackSpec,
    ChangeRequest,
    EvidenceSubject,
    Finding,
    RunEvent,
    WorkerKind,
)
from gauntlet.contracts.events import PayloadValue
from gauntlet.domain import Attribution, GateStatus, Severity
from gauntlet.execution.environment_pair import GateEnvironmentPair, gate_environment_pair
from gauntlet.planning import FrozenPlan
from gauntlet.ports import EnvironmentUnavailableError, RunStore, SandboxProvider

from .attempts import AttemptExecutor
from .pair_verdict import GateAttempt, PairedGateVerdict, adjudicate_ui_pair
from .plan_change import PlanChangeUseCase

ACTOR: Final = "gate-runner"
MIN_ATTEMPTS_PER_SIDE: Final = 2

PairAdjudicator = Callable[..., PairedGateVerdict]
"""Signature of ``adjudicate_ui_pair``: keyword args change, attack, run_id, fixture_checksum,
head, base."""

_SEVERITY: Final = {
    GateStatus.CONFIRMED_REGRESSION: Severity.HIGH,
    GateStatus.CONFIRMED_PRE_EXISTING: Severity.MEDIUM,
    GateStatus.CONFIRMED_POLICY_VIOLATION: Severity.HIGH,
    GateStatus.SUSPECTED: Severity.MEDIUM,
}


@dataclass(frozen=True)
class WorkerRoute:
    """How one worker kind is executed and judged."""

    executor: AttemptExecutor
    adjudicate: PairAdjudicator = adjudicate_ui_pair


@dataclass(frozen=True)
class GateDependencies:
    plan_change: PlanChangeUseCase
    sandbox: SandboxProvider
    routes: Mapping[WorkerKind, WorkerRoute]
    store: RunStore
    clock: Callable[[], datetime]
    new_id: Callable[[str], str]
    """Returns a fresh unique identifier with the given prefix."""
    attempts_per_side: int = MIN_ATTEMPTS_PER_SIDE


@dataclass(frozen=True)
class AttackOutcome:
    attack: AttackSpec
    finding: Finding
    head: tuple[GateAttempt, ...] = ()
    base: tuple[GateAttempt, ...] = ()


@dataclass(frozen=True)
class GateRunReport:
    run_id: str
    plan: FrozenPlan
    outcomes: tuple[AttackOutcome, ...]
    events: tuple[RunEvent, ...] = field(default=())

    @property
    def findings(self) -> tuple[Finding, ...]:
        return tuple(outcome.finding for outcome in self.outcomes)

    @property
    def overall(self) -> GateStatus:
        """Most severe status across attacks; ``not_tested`` when nothing ran."""
        order = (
            GateStatus.CONFIRMED_REGRESSION,
            GateStatus.CONFIRMED_POLICY_VIOLATION,
            GateStatus.CONFIRMED_PRE_EXISTING,
            GateStatus.SUSPECTED,
            GateStatus.ENVIRONMENT_ERROR,
            GateStatus.NOT_REPRODUCIBLE,
            GateStatus.PASSED,
        )
        statuses = {finding.status for finding in self.findings}
        return next((status for status in order if status in statuses), GateStatus.NOT_TESTED)


def _unsupported_finding(attack: AttackSpec, reason: str, status: GateStatus) -> Finding:
    return Finding(
        finding_id=f"finding-{attack.attack_id}",
        attack_id=attack.attack_id,
        status=status,
        attribution=Attribution.UNKNOWN,
        severity=Severity.INFO,
        oracle_ids=attack.oracle_ids,
        head_reproductions=0,
        head_attempts=0,
        base_reproductions=0,
        base_attempts=0,
        limitations=(reason,),
    )


class RunGateUseCase:
    def __init__(self, deps: GateDependencies) -> None:
        if deps.attempts_per_side < MIN_ATTEMPTS_PER_SIDE:
            raise ValueError("Gate needs at least two attempts per revision")
        self._deps = deps

    async def execute(
        self, run_id: str, change: ChangeRequest, fixture_checksum: str
    ) -> GateRunReport:
        plan = await self._deps.plan_change.execute(run_id, change)
        runnable = [a for a in plan.attacks if a.worker_kind in self._deps.routes]
        outcomes: dict[str, AttackOutcome] = {
            attack.attack_id: AttackOutcome(
                attack,
                _unsupported_finding(
                    attack,
                    f"no registered executor for worker '{attack.worker_kind}'",
                    GateStatus.NOT_TESTED,
                ),
            )
            for attack in plan.attacks
            if attack.worker_kind not in self._deps.routes
        }
        if runnable:
            try:
                async with gate_environment_pair(
                    self._deps.sandbox, change, fixture_checksum
                ) as pair:
                    await self._append(
                        run_id,
                        "environments_ready",
                        {
                            "base_environment_id": pair.base.environment_id,
                            "head_environment_id": pair.head.environment_id,
                            "fixture_checksum": fixture_checksum,
                        },
                    )
                    for attack in runnable:
                        outcomes[attack.attack_id] = await self._run_attack(
                            run_id, change, attack, pair, fixture_checksum
                        )
            except EnvironmentUnavailableError:
                for attack in runnable:
                    if attack.attack_id not in outcomes:
                        outcomes[attack.attack_id] = AttackOutcome(
                            attack,
                            _unsupported_finding(
                                attack,
                                "isolated base/head environments were unavailable",
                                GateStatus.ENVIRONMENT_ERROR,
                            ),
                        )
        ordered = tuple(outcomes[a.attack_id] for a in plan.attacks)
        report = GateRunReport(run_id, plan, ordered)
        await self._append(
            run_id,
            "run_completed",
            {
                "plan_hash": plan.plan_hash,
                "overall_status": report.overall.value,
                "findings": len(ordered),
                "not_tested_reason": plan.not_tested_reason,
            },
        )
        events = tuple(await self._deps.store.list_events(run_id))
        return GateRunReport(run_id, plan, ordered, events)

    async def _run_attack(
        self,
        run_id: str,
        change: ChangeRequest,
        attack: AttackSpec,
        pair: GateEnvironmentPair,
        fixture_checksum: str,
    ) -> AttackOutcome:
        route = self._deps.routes[attack.worker_kind]
        attempts: dict[str, list[GateAttempt]] = {"head": [], "base": []}
        # Interleave head/base so drift over time affects both sides alike.
        for index in range(self._deps.attempts_per_side):
            for side, environment in (("head", pair.head), ("base", pair.base)):
                subject = EvidenceSubject(
                    run_id=run_id,
                    attempt_id=self._deps.new_id("attempt"),
                    observation_id=self._deps.new_id("observation"),
                    environment_id=environment.environment_id,
                    source_sha=environment.source_sha,
                    fixture_checksum=environment.fixture_checksum,
                    collector=route.executor.collector,
                )
                attempt = await route.executor.attempt(attack, environment, subject)
                attempts[side].append(attempt)
                await self._append(
                    run_id,
                    "attempt_recorded",
                    {
                        "attack_id": attack.attack_id,
                        "side": side,
                        "index": index,
                        "attempt_id": subject.attempt_id,
                        "observation_status": attempt.observation.status,
                        "oracle_outcomes": ",".join(v.outcome.value for v in attempt.verdicts),
                        "evidence_count": len(attempt.observation.evidence_ids),
                    },
                    key=f"{run_id}:attempt:{subject.attempt_id}",
                )
        verdict = route.adjudicate(
            change=change,
            attack=attack,
            run_id=run_id,
            fixture_checksum=fixture_checksum,
            head=attempts["head"],
            base=attempts["base"],
        )
        finding = self._finding(attack, verdict)
        await self._append(
            run_id,
            "finding_recorded",
            {
                "attack_id": attack.attack_id,
                "finding_id": finding.finding_id,
                "status": finding.status.value,
                "attribution": finding.attribution.value,
                "head": f"{verdict.head_failures}/{verdict.head_attempts}",
                "base": f"{verdict.base_failures}/{verdict.base_attempts}",
                "evidence_ids": ",".join(finding.evidence_ids) or None,
            },
            key=f"{run_id}:finding:{attack.attack_id}",
        )
        return AttackOutcome(attack, finding, tuple(attempts["head"]), tuple(attempts["base"]))

    def _finding(self, attack: AttackSpec, verdict: PairedGateVerdict) -> Finding:
        status = verdict.verdict.status
        return Finding(
            finding_id=f"finding-{attack.attack_id}",
            attack_id=attack.attack_id,
            status=status,
            attribution=verdict.verdict.attribution,
            severity=_SEVERITY.get(status, Severity.INFO),
            oracle_ids=attack.oracle_ids,
            oracle_verdict_ids=verdict.oracle_verdict_ids,
            head_reproductions=verdict.head_failures,
            head_attempts=verdict.head_attempts,
            base_reproductions=verdict.base_failures,
            base_attempts=verdict.base_attempts,
            evidence_ids=verdict.evidence_ids,
            limitations=tuple(item[:2500] for item in verdict.limitations),
        )

    async def _append(
        self,
        run_id: str,
        event_type: str,
        payload: dict[str, PayloadValue],
        *,
        key: str | None = None,
    ) -> None:
        existing: Sequence[RunEvent] = await self._deps.store.list_events(run_id)
        sequence = existing[-1].sequence + 1 if existing else 0
        await self._deps.store.append_event(
            RunEvent(
                run_id=run_id,
                event_id=self._deps.new_id("event"),
                sequence=sequence,
                created_at=self._deps.clock(),
                actor=ACTOR,
                event_type=event_type,
                idempotency_key=key or f"{run_id}:{event_type}",
                payload=payload,
            )
        )
