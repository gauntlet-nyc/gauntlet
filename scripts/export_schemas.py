"""Owner A: export canonical JSON schemas from Pydantic, not handwritten wire types."""

import json
from pathlib import Path

from gauntlet.contracts import (
    AttackSpec, ChangeImpactMap, ChangeRequest, Finding, HistoricalDecision,
    Observation, RecallTrigger, RecallVerdict, ReplaySpec, RunEvent,
)

MODELS = [
    AttackSpec, ChangeImpactMap, ChangeRequest, Finding, HistoricalDecision,
    Observation, RecallTrigger, RecallVerdict, ReplaySpec, RunEvent,
]


def main() -> None:
    target = Path(__file__).resolve().parents[1] / "packages/contracts/jsonschema"
    target.mkdir(parents=True, exist_ok=True)
    for model in MODELS:
        filename = "".join(("-" + c.lower()) if c.isupper() else c for c in model.__name__).lstrip("-")
        (target / f"{filename}.v1.json").write_text(
            json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(f"Exported {len(MODELS)} schemas to {target}")


if __name__ == "__main__":
    main()
