"""Run Recall over Cartwheel's seeded refund-agent history. Offline by default.

    uv run python scripts/run_recall.py                    # trigger: KB chunk kb-117
    uv run python scripts/run_recall.py --kind memory --reference mem-083
    RUN_LIVE_INTEGRATIONS=1 uv run python scripts/run_recall.py --model azure   # model replays

Lineage finds decisions exposed to the trigger (direct and second order), the pinned control
replay must reproduce each original decision, and the counterfactual removes the source.
The event audit checks every recorded request_refund against the authoritative ledger.
Remediation output is review-queue drafts only.
"""

import argparse
import asyncio
import json
from datetime import datetime
from uuid import uuid4

from gauntlet.composition import build_recall
from gauntlet.contracts import RecallTrigger
from gauntlet.settings import MissingSettingError, Settings


async def run(args: argparse.Namespace) -> dict[str, object]:
    runtime = build_recall(Settings.from_env(), model=args.model)
    manifest = runtime.archive.manifest
    trigger = RecallTrigger(
        trigger_id=f"trigger-{args.kind}-{args.reference}",
        kind=args.kind,
        reference=args.reference,
        mode="decision_counterfactual",
        start_at=datetime.fromisoformat(manifest["window_start"]),
        end_at=datetime.fromisoformat(manifest["window_end"]),
        target_id=manifest["target_id"],
    )
    recall_id = args.recall_id or f"recall-{uuid4().hex[:12]}"
    report = await runtime.use_case.execute(recall_id, trigger, audit_tool=args.audit_tool)
    audit = report.audit
    return {
        "mode": "offline" if args.model == "scripted" else "live_model_replay",
        "adapters": runtime.labels,
        "history_checksum": runtime.archive.checksum,
        "recall_id": recall_id,
        "trigger": trigger.model_dump(mode="json"),
        "counts": {k: v for k, v in report.counts().items() if v},
        "decisions": [
            {
                "decision_id": item.verdict.decision_id,
                "exposure": "direct" if item.exposure.direct else "second_order",
                "path": " -> ".join(
                    [item.exposure.trigger_node.node_id]
                    + [f"{e.relation}:{e.target.node_id}" for e in item.exposure.path]
                ),
                "classification": item.verdict.classification.value,
                "control_matches": item.verdict.control_matches,
                "material_change": item.verdict.material_change,
                "rationale": item.verdict.rationale,
                "replays": len(item.verdict.replay_ids),
            }
            for item in report.decisions
        ],
        "gaps": list(report.gaps),
        "event_audit": None
        if audit is None
        else {
            "summary": audit.summary.model_dump(mode="json"),
            "violations": [
                {
                    "tool_event_id": v.tool_event_id,
                    "decision_id": v.decision_id,
                    "rationale": v.rationale,
                    "evidence_ids": list(v.evidence_ids),
                }
                for v in audit.verdicts
                if v.classification.value == "audit_violation"
            ],
            "inconclusive": [
                {"tool_event_id": v.tool_event_id, "limitations": list(v.limitations)}
                for v in audit.verdicts
                if v.classification.value == "inconclusive"
            ],
            "proposals": [p.model_dump(mode="json") for p in audit.proposals],
        },
        "review_queue": [p.model_dump(mode="json") for p in report.proposals],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--kind",
        choices=("document", "memory", "model_version", "prompt_version", "policy_version"),
        default="document",
    )
    parser.add_argument("--reference", default="kb-117")
    parser.add_argument("--audit-tool", default="request_refund")
    parser.add_argument("--recall-id")
    parser.add_argument("--model", choices=("scripted", "azure", "bedrock"), default="scripted")
    args = parser.parse_args()
    try:
        result = asyncio.run(run(args))
    except (MissingSettingError, ValueError, RuntimeError) as exc:
        print(json.dumps({"status": "not_tested", "error": str(exc)}))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
