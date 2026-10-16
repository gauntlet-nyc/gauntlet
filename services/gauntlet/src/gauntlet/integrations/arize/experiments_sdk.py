"""Arize Experiments via the official SDK (`arize==8.59.1`, `live-providers`, lazy import).

Publishes one Recall counterfactual study as an Arize experiment in the configured space:
one run per replayed decision, with the counterfactual action as the run output, the
control result alongside it, and an evaluator column carrying the verdict (`tainted`,
`cleared`, `inconclusive`, ...) plus a 1/0 materiality score. The verdict comes from
Gauntlet's domain rules; Arize only stores and displays it. No customer content is sent:
decision IDs, action names, statuses and booleans only.

The OTLP experiment traces in `experiments.py` stay as they are; this adds the real
Experiments object so it shows up in the AX Experiments UI.
"""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final

from gauntlet.ports.errors import EnvironmentUnavailableError
from gauntlet.settings import IntegrationSettings, require

MAX_RUNS: Final = 1000  # REST limit for experiments not attached to a dataset


@dataclass(frozen=True)
class RecallExperimentRow:
    decision_id: str
    control_replay_id: str
    control_status: str
    control_action: str | None
    counterfactual_replay_id: str
    counterfactual_status: str
    counterfactual_action: str | None
    control_matches: bool
    material_change: bool
    verdict: str


def experiment_runs(rows: Sequence[RecallExperimentRow]) -> list[dict[str, object]]:
    return [
        {
            "output": row.counterfactual_action or f"<{row.counterfactual_status}>",
            "decision_id": row.decision_id,
            "control_replay_id": row.control_replay_id,
            "control_status": row.control_status,
            "control_action": row.control_action or f"<{row.control_status}>",
            "counterfactual_replay_id": row.counterfactual_replay_id,
            "counterfactual_status": row.counterfactual_status,
            "control_matches": row.control_matches,
            "material_change": row.material_change,
            "verdict": row.verdict,
            "material_score": 1.0 if row.material_change else 0.0,
        }
        for row in rows
    ]


class ArizeExperimentPublisher:
    def __init__(self, client: Any, *, space: str) -> None:  # noqa: ANN401 - SDK boundary
        if not space:
            raise ValueError("Arize space is required")
        self._client = client
        self._space = space

    @classmethod
    def from_settings(cls, settings: IntegrationSettings) -> "ArizeExperimentPublisher":
        if not settings.core.run_live_integrations:
            raise EnvironmentUnavailableError("missing RUN_LIVE_INTEGRATIONS=1 for Arize")
        config = require("arize", settings.arize)
        try:
            from arize import ArizeClient
        except ImportError:
            raise EnvironmentUnavailableError("missing arize SDK (live-providers group)") from None
        return cls(ArizeClient(api_key=config.api_key.reveal()), space=config.space_id.reveal())

    async def publish(self, name: str, rows: Sequence[RecallExperimentRow]) -> str:
        """Create the experiment; return Arize's experiment ID."""
        if not rows or len(rows) > MAX_RUNS:
            raise ValueError(f"an experiment needs 1..{MAX_RUNS} runs")
        try:
            from arize.experiments.evaluators.types import EvaluationResultFieldNames
            from arize.experiments.types import ExperimentTaskFieldNames
        except ImportError:
            raise EnvironmentUnavailableError("missing arize SDK (live-providers group)") from None
        runs = experiment_runs(rows)

        def create() -> object:
            return self._client.experiments.create(
                name=name,
                space=self._space,
                experiment_runs=runs,
                task_fields=ExperimentTaskFieldNames(output="output"),
                evaluator_columns={
                    "counterfactual_materiality": EvaluationResultFieldNames(
                        score="material_score", label="verdict"
                    )
                },
                force_http=True,
            )

        try:
            experiment = await asyncio.to_thread(create)
        except Exception as exc:
            raise EnvironmentUnavailableError(
                f"Arize experiment create failed ({type(exc).__name__})"
            ) from None
        experiment_id = getattr(experiment, "id", None)
        if not isinstance(experiment_id, str) or not experiment_id:
            raise EnvironmentUnavailableError("Arize returned no experiment ID")
        return experiment_id
