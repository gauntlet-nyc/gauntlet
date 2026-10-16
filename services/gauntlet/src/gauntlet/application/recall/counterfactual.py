"""Recall `decision_counterfactual` for one exposed decision (master plan Sections 3.2, 9.3).

(A) original recorded outcome → (B) control replays with every input pinned, suspect source
kept → (C) counterfactual replays with exactly that source removed. `tainted` requires every
control run to reproduce the original and every counterfactual run to agree on a materially
different outcome. Temperature 0 alone is not determinism, so runs are repeated.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

from gauntlet.contracts import (
    ExposureRecord,
    HistoricalDecision,
    RecallVerdict,
    ReplayResult,
    ReplaySpec,
)
from gauntlet.domain import (
    ControlComparison,
    DecisionOutcome,
    MaterialityPolicy,
    RecallClassification,
    ReplayStatus,
    classify_counterfactual,
    distribution,
)
from gauntlet.ports import ReplayEngine, ReplayWorld, ReplayWorldResolver

from .readiness import ReplayReadiness

_REMOVABLE_SOURCES: Final = frozenset({"document_chunk", "memory"})
_RUN_FAILURES: Final = frozenset({ReplayStatus.ENVIRONMENT_ERROR, ReplayStatus.NOT_REPLAYABLE})


@dataclass(frozen=True)
class CounterfactualSettings:
    repeats: int = 3
    max_runtime_seconds: int = 180
    policy: MaterialityPolicy = MaterialityPolicy()


def _outcome(result: ReplayResult) -> DecisionOutcome:
    return DecisionOutcome(result.observed_action, result.amount_minor)


def _describe(outcome: DecisionOutcome) -> str:
    amount = "no amount" if outcome.amount_minor is None else f"amount {outcome.amount_minor}"
    return f"{outcome.action or 'no action'} ({amount})"


class CounterfactualUseCase:
    def __init__(
        self,
        engine: ReplayEngine,
        worlds: ReplayWorldResolver,
        settings: CounterfactualSettings | None = None,
    ) -> None:
        self._engine = engine
        self._worlds = worlds
        self._settings = settings or CounterfactualSettings()
        if self._settings.repeats < 2:
            raise ValueError("at least two runs per arm are needed to detect nondeterminism")

    async def evaluate(
        self,
        recall_id: str,
        exposure: ExposureRecord,
        decision: HistoricalDecision,
        readiness: ReplayReadiness,
    ) -> RecallVerdict:
        policy = self._settings.policy
        original = DecisionOutcome(decision.structured_action, decision.amount_minor)
        if not readiness.replayable:
            missing = ", ".join(m.field for m in readiness.missing if m.critical)
            return self._verdict(
                recall_id, decision, RecallClassification.NOT_REPLAYABLE,
                f"Critical inputs were not recorded: {missing}", (), None, None,
            )  # fmt: skip
        if exposure.trigger_node.kind not in _REMOVABLE_SOURCES:
            return self._verdict(
                recall_id, decision, RecallClassification.INCONCLUSIVE,
                f"No counterfactual mutation is defined for a {exposure.trigger_node.kind} trigger",
                (), None, None,
            )  # fmt: skip
        world = await self._worlds.world_for(decision)
        if world is None:
            return self._verdict(
                recall_id, decision, RecallClassification.NOT_REPLAYABLE,
                "The historical environment could not be reconstructed", (), None, None,
            )  # fmt: skip

        control = await self._run(recall_id, decision, world, exposure, "control")
        replay_ids = tuple(r.replay_id for r in control)
        if any(r.status in _RUN_FAILURES for r in control):
            return self._verdict(
                recall_id, decision, RecallClassification.INCONCLUSIVE,
                "A control replay failed to run", replay_ids, None, None,
            )  # fmt: skip
        control_dist = distribution([_outcome(r) for r in control], policy)
        control_matches = control_dist.stable and not policy.differs(
            control_dist.outcomes[0], original
        )
        if not control_matches:
            seen = "; ".join(sorted({_describe(o) for o in control_dist.outcomes}))
            return self._verdict(
                recall_id, decision, RecallClassification.INCONCLUSIVE,
                f"Control did not reproduce {_describe(original)}; observed {seen}",
                replay_ids, False, None,
            )  # fmt: skip

        counter = await self._run(recall_id, decision, world, exposure, "counterfactual")
        replay_ids += tuple(r.replay_id for r in counter)
        environment_ok = not any(r.status in _RUN_FAILURES for r in counter)
        counter_dist = distribution([_outcome(r) for r in counter], policy)
        material: bool | None = None
        if environment_ok and counter_dist.stable:
            material = policy.differs(counter_dist.outcomes[0], original)
        classification = classify_counterfactual(
            ControlComparison(True, environment_ok, True, material)
        )
        if classification is RecallClassification.TAINTED:
            rationale = (
                f"Control reproduced {_describe(original)}; without "
                f"{exposure.trigger_node.node_id} the agent chose "
                f"{_describe(counter_dist.outcomes[0])}"
            )
        elif classification is RecallClassification.CLEARED:
            rationale = (
                f"Removing {exposure.trigger_node.node_id} did not change {_describe(original)}"
            )
        else:
            rationale = "Counterfactual runs failed or disagreed; outcome is not determinable"
        return self._verdict(
            recall_id, decision, classification, rationale, replay_ids, True, material
        )

    async def _run(
        self,
        recall_id: str,
        decision: HistoricalDecision,
        world: ReplayWorld,
        exposure: ExposureRecord,
        arm: Literal["control", "counterfactual"],
    ) -> Sequence[ReplayResult]:
        results: list[ReplayResult] = []
        for run in range(self._settings.repeats):
            spec = self._spec(recall_id, decision, world, exposure, arm, run)
            results.append(await self._engine.replay(spec))
        return results

    def _spec(
        self,
        recall_id: str,
        decision: HistoricalDecision,
        world: ReplayWorld,
        exposure: ExposureRecord,
        arm: Literal["control", "counterfactual"],
        run: int,
    ) -> ReplaySpec:
        source = exposure.trigger_node.node_id
        counterfactual = arm == "counterfactual"
        return ReplaySpec(
            replay_id=f"{recall_id}:{decision.decision_id}:{arm}:{run}",
            mode="historical_counterfactual" if counterfactual else "historical_control",
            target_id=decision.target_id,
            source_sha=world.source_sha,
            image_digest=world.image_digest,
            fixture_id=world.fixture_id,
            fixture_checksum=world.fixture_checksum,
            decision_id=decision.decision_id,
            model_id=decision.model_id,
            prompt_version=decision.prompt_version,
            policy_version=decision.policy_version,
            kb_snapshot_hash=decision.kb_snapshot_hash,
            memory_snapshot_hash=decision.memory_snapshot_hash,
            tool_results_hash=decision.tool_results_hash,
            input_messages_hash=decision.input_messages_hash,
            seed=run,
            logical_timestamp=decision.occurred_at,
            excluded_source_id=source if counterfactual else None,
            mutation_description=(
                f"Remove {exposure.trigger_node.kind} {source}; every other input pinned"
                if counterfactual
                else None
            ),
            max_runtime_seconds=self._settings.max_runtime_seconds,
        )

    def _verdict(
        self,
        recall_id: str,
        decision: HistoricalDecision,
        classification: RecallClassification,
        rationale: str,
        replay_ids: tuple[str, ...],
        control_matches: bool | None,
        material: bool | None,
    ) -> RecallVerdict:
        return RecallVerdict(
            verdict_id=f"{recall_id}:{decision.decision_id}",
            recall_id=recall_id,
            decision_id=decision.decision_id,
            mode="decision_counterfactual",
            classification=classification,
            rationale=rationale[:2500],
            criterion_version=self._settings.policy.version,
            control_matches=control_matches,
            material_change=material,
            replay_ids=replay_ids,
        )
