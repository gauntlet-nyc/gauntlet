"""Recall control-vs-counterfactual comparisons recorded as an Arize experiment trace.

One root span per experiment (`experiment.id`), one child per variant (`control`,
`counterfactual`) with the replay outcome, and an EVALUATOR child with the materiality
result. The verdict itself comes from `domain`/`application`, never from tracing.

The Arize experiments REST/SDK API (`arize` package) is not an approved dependency; until
it is, experiments are visible as tagged traces in the project, which Arize can filter.
"""

from dataclasses import dataclass

from gauntlet.contracts import ReplayResult

from .tracing import Tracer


@dataclass(frozen=True)
class ExperimentRecord:
    experiment_id: str
    trace_id: str
    variants: int


async def record_counterfactual_experiment(
    tracer: Tracer,
    *,
    experiment_id: str,
    decision_id: str,
    control: ReplayResult,
    counterfactual: ReplayResult,
    control_matches: bool,
    material_change: bool,
    verdict: str,
) -> ExperimentRecord:
    async with tracer.span(
        "recall.experiment",
        "AGENT",
        {
            "experiment.id": experiment_id,
            "experiment.name": f"recall-counterfactual-{decision_id}",
            "gauntlet.decision_id": decision_id,
        },
    ) as root:
        for variant, result in (("control", control), ("counterfactual", counterfactual)):
            async with tracer.span(
                f"recall.experiment.{variant}",
                "CHAIN",
                {
                    "experiment.id": experiment_id,
                    "experiment.variant": variant,
                    "gauntlet.replay_id": result.replay_id,
                    "gauntlet.replay_status": result.status,
                    "gauntlet.observed_action": result.observed_action,
                    "gauntlet.amount_minor": result.amount_minor,
                },
            ):
                pass
        async with tracer.span(
            "recall.experiment.eval",
            "EVALUATOR",
            {
                "experiment.id": experiment_id,
                "eval.control_matches": control_matches,
                "eval.material_change": material_change,
                "eval.label": verdict,
            },
        ):
            pass
        return ExperimentRecord(experiment_id=experiment_id, trace_id=root.trace_id, variants=2)
