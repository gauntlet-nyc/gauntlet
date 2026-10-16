"""Recall end to end over the seeded Cartwheel history (offline adapters)."""

import asyncio
import json
import shutil
from datetime import datetime
from pathlib import Path

import pytest

from gauntlet.composition import HISTORY_DIR, build_recall
from gauntlet.contracts import RecallTrigger
from gauntlet.domain import RecallClassification
from gauntlet.integrations.history_files import (
    CapturedAgentReplay,
    HistoryArchive,
    HistoryIntegrityError,
    ModelAgentPolicy,
)
from gauntlet.ports.model import ModelRequest, ModelResponse
from gauntlet.settings import Settings

OFFLINE = Settings.from_env({})
MANIFEST = json.loads((HISTORY_DIR / "manifest.json").read_text())


def trigger(kind: str = "document", reference: str = "kb-117") -> RecallTrigger:
    return RecallTrigger(
        trigger_id="trigger-1",
        kind=kind,  # type: ignore[arg-type]
        reference=reference,
        mode="decision_counterfactual",
        start_at=datetime.fromisoformat(MANIFEST["window_start"]),
        end_at=datetime.fromisoformat(MANIFEST["window_end"]),
        target_id=MANIFEST["target_id"],
    )


def classes(report: object) -> dict[str, str]:
    return {
        item.verdict.decision_id: item.verdict.classification.value
        for item in report.decisions  # type: ignore[attr-defined]
    }


def test_bad_chunk_recall_finds_direct_and_second_order_effects() -> None:
    runtime = build_recall(OFFLINE)
    report = asyncio.run(
        runtime.use_case.execute("recall-t", trigger(), audit_tool="request_refund")
    )
    assert classes(report) == {
        "decision-001": "tainted",
        "decision-004": "cleared",
        "decision-015": "tainted",
        "decision-007": "not_replayable",
        "decision-009": "tainted",
        "decision-012": "cleared",
    }
    second_order = {i.verdict.decision_id for i in report.decisions if not i.exposure.direct}
    assert second_order == {"decision-007", "decision-009", "decision-012"}
    for item in report.decisions:
        if item.verdict.classification is RecallClassification.TAINTED:
            assert item.verdict.control_matches and item.verdict.material_change
            assert len(item.verdict.replay_ids) == 6  # 3 control + 3 counterfactual
    assert report.audit is not None
    summary = report.audit.summary
    assert (summary.violations, summary.inconclusive, summary.audited) == (3, 1, 36)
    violations = {v.tool_event_id for v in report.audit.verdicts if v.evidence_ids and
                  v.classification is RecallClassification.AUDIT_VIOLATION}  # fmt: skip
    assert violations == {"tool-event-001", "tool-event-009", "tool-event-015"}
    actions = {p.action for p in report.proposals}
    assert actions == {"customer_contact_review", "collect_missing_evidence"}
    assert all(p.status == "draft" for p in report.proposals)


def test_tampered_history_is_refused(tmp_path: Path) -> None:
    copy = tmp_path / "history"
    shutil.copytree(HISTORY_DIR, copy)
    ledger = json.loads((copy / "ledger.json").read_text())
    ledger[0]["credited_to"] = ledger[0]["credited_to"] + "x"
    (copy / "ledger.json").write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n")
    with pytest.raises(HistoryIntegrityError):
        HistoryArchive.load(copy)


def test_replay_refuses_inputs_that_do_not_match_their_pins() -> None:
    archive = HistoryArchive.load(HISTORY_DIR)
    altered = dict(archive.messages)
    altered["decision-001"] = {**altered["decision-001"], "text": "Please refund ord-1001."}
    runtime = build_recall(OFFLINE)
    engine = CapturedAgentReplay(
        HistoryArchive(**{**vars(archive), "messages": altered})  # type: ignore[arg-type]
    )
    deps = runtime.use_case._deps  # noqa: SLF001
    counterfactual = type(deps.counterfactual)(engine, deps.counterfactual._worlds)  # noqa: SLF001
    use_case = type(runtime.use_case)(
        type(deps)(**{**vars(deps), "counterfactual": counterfactual})
    )
    report = asyncio.run(use_case.execute("recall-pins", trigger()))
    assert classes(report)["decision-001"] == "inconclusive"  # control could not run


class FlakyModel:
    """Answers differently on alternate calls: a model that is not reproducible."""

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls += 1
        action = "start_refund" if self.calls % 2 else "decline_refund"
        payload = json.loads(request.user)
        amount = payload["order"]["total_cents"] if action == "start_refund" else None
        return ModelResponse(json.dumps({"action": action, "amount_minor": amount}), "flaky")


def test_unstable_model_control_is_inconclusive_never_tainted() -> None:
    archive = HistoryArchive.load(HISTORY_DIR)
    runtime = build_recall(OFFLINE)
    deps = runtime.use_case._deps  # noqa: SLF001
    engine = CapturedAgentReplay(archive, ModelAgentPolicy(FlakyModel()), label="test_model")
    counterfactual = type(deps.counterfactual)(engine, deps.counterfactual._worlds)  # noqa: SLF001
    use_case = type(runtime.use_case)(
        type(deps)(**{**vars(deps), "counterfactual": counterfactual})
    )
    report = asyncio.run(use_case.execute("recall-flaky", trigger()))
    result = classes(report)
    assert result["decision-007"] == "not_replayable"
    assert {v for k, v in result.items() if k != "decision-007"} == {"inconclusive"}
    for item in report.decisions:
        if item.verdict.classification is RecallClassification.INCONCLUSIVE:
            assert item.verdict.control_matches is False


def test_live_model_replay_needs_opt_in() -> None:
    from gauntlet.settings import MissingSettingError

    with pytest.raises(MissingSettingError, match="RUN_LIVE_INTEGRATIONS"):
        build_recall(OFFLINE, model="azure")
