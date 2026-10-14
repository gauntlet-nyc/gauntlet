"""Every golden example parses into its canonical model and round-trips without loss."""

import json
from pathlib import Path

import pytest
from gauntlet.contracts import (
    AttackSpec,
    ChangeImpactMap,
    ChangeRequest,
    EvidenceBinding,
    Finding,
    HistoricalDecision,
    Observation,
    OracleVerdict,
    RecallTrigger,
    RecallVerdict,
    ReplayResult,
    ReplaySpec,
    RunEvent,
    StrictDTO,
)

EXAMPLES_DIR = Path(__file__).resolve().parents[3] / "docs" / "contracts" / "examples"

GOLDENS: dict[str, type[StrictDTO]] = {
    "ai-plan.v1.json": AttackSpec,
    "change-impact-map.v1.json": ChangeImpactMap,
    "change-request.v1.json": ChangeRequest,
    "evidence-binding.v1.json": EvidenceBinding,
    "finding.v1.json": Finding,
    "historical-decision.v1.json": HistoricalDecision,
    "observation.v1.json": Observation,
    "oracle-verdict.v1.json": OracleVerdict,
    "recall-trigger.v1.json": RecallTrigger,
    "recall-verdict-tainted.v1.json": RecallVerdict,
    "recall-verdict.v1.json": RecallVerdict,
    "replay-result.v1.json": ReplayResult,
    "replay-spec-control.v1.json": ReplaySpec,
    "replay-spec-counterfactual.v1.json": ReplaySpec,
    "run-event.v1.json": RunEvent,
    "ui-plan.v1.json": AttackSpec,
}


def test_every_example_file_has_a_model() -> None:
    on_disk = {p.name for p in EXAMPLES_DIR.glob("*.json")}
    assert on_disk == set(GOLDENS)


@pytest.mark.parametrize(("filename", "model"), sorted(GOLDENS.items()))
def test_golden_round_trips(filename: str, model: type[StrictDTO]) -> None:
    raw = json.loads((EXAMPLES_DIR / filename).read_text(encoding="utf-8"))
    parsed = model.model_validate(raw)
    assert parsed.model_dump(mode="json") == raw
