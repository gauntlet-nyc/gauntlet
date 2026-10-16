"""C-04 fixture: seeded history satisfies A-04 contracts and the Phase 4 gate shape."""

import importlib.util
import json
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

import pytest

from gauntlet.application.recall import RecallScoper, assess_readiness
from gauntlet.contracts import HistoricalDecision, LineageEdge, NodeRef, RecallTrigger, ToolEvent

ROOT = Path(__file__).resolve().parents[3]
HISTORY = ROOT / "apps/cartwheel/history"


def _load(name: str) -> object:
    return json.loads((HISTORY / name).read_text())


def _builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "build_cartwheel_history", ROOT / "scripts/build_cartwheel_history.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


EDGES = [LineageEdge.model_validate(e) for e in _load("lineage_edges.json")]  # type: ignore[attr-defined]
DECISIONS = {
    d["decision_id"]: HistoricalDecision.model_validate(d)
    for d in _load("decisions.json")  # type: ignore[attr-defined]
}


class Lineage:
    async def edges_from(self, node: NodeRef) -> Sequence[LineageEdge]:
        return [e for e in EDGES if e.source == node]

    async def edges_to(self, node: NodeRef) -> Sequence[LineageEdge]:
        return [e for e in EDGES if e.target == node]


class History:
    async def get_decision(self, decision_id: str) -> HistoricalDecision | None:
        return DECISIONS.get(decision_id)


def test_committed_history_matches_regeneration(tmp_path: Path) -> None:
    files, _ = _builder().build()
    checksum = _builder().write(tmp_path / "h", files)
    assert checksum == json.loads((HISTORY / "manifest.json").read_text())["checksum_sha256"]
    for path in (tmp_path / "h").iterdir():
        assert path.read_text() == (HISTORY / path.name).read_text()


def test_committed_history_contains_no_scoring_truth() -> None:
    text = "\n".join(p.read_text().lower() for p in HISTORY.iterdir())
    for banned in ("poison", 'truth":', "malicious", "attack", "changed_by", "affected"):
        assert banned not in text


def test_tool_events_and_ledger_are_consistent() -> None:
    events = [ToolEvent.model_validate(e) for e in _load("tool_events.json")]  # type: ignore[attr-defined]
    ledger = {entry["event_id"] for entry in _load("ledger.json")}  # type: ignore[attr-defined]
    for event in events:
        assert event.decision_id in DECISIONS
        assert (event.outcome == "succeeded") == (event.event_id in ledger)


@pytest.mark.asyncio
async def test_phase4_gate_shape_exposure_and_replayability() -> None:
    trigger = RecallTrigger.model_validate(
        {
            "trigger_id": "trig-kb-117",
            "kind": "document",
            "reference": "kb-117",
            "mode": "decision_counterfactual",
            "start_at": "2026-10-07T00:00:00Z",
            "end_at": "2026-10-14T12:00:00Z",
            "target_id": "cartwheel-fixture",
        }
    )
    scope = await RecallScoper(Lineage(), History()).trace("recall-1", trigger)
    direct = {e.decision_id for e in scope.exposures if e.direct}
    via_memory = {e.decision_id for e in scope.exposures if not e.direct}
    assert direct == {"decision-001", "decision-004", "decision-015"}
    assert via_memory == {"decision-007", "decision-009", "decision-012"}
    unreplayable = []
    for exposure in scope.exposures:
        decision = DECISIONS[exposure.decision_id]
        incoming = await Lineage().edges_to(NodeRef(kind="decision", node_id=exposure.decision_id))
        if not assess_readiness(decision, incoming).replayable:
            unreplayable.append(exposure.decision_id)
    assert unreplayable == ["decision-007"]
