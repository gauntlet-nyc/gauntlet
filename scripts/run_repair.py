"""P3 repair on the refund-tool finding. Two steps; a human approves the exact plan hash.

    # 1. Gate + fix proposal. Prints the plan, its SHA-256 and touched paths. Writes nothing.
    uv run python scripts/run_repair.py --run-id demo-1
    # 2. A reviewer approves that exact hash (token from GAUNTLET_REVIEWER_TOKENS, read from
    #    the environment, never argv), the patch is applied in a fresh worktree and re-verified.
    GAUNTLET_REVIEWER_TOKENS=alice:<16+ chars> GAUNTLET_REVIEWER_TOKEN=<same token> \
        uv run python scripts/run_repair.py --run-id demo-1 --approve-hash <sha256>

The release verdict is review-only. Nothing is merged, pushed or deployed.
"""

import argparse
import asyncio
import hmac
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_cartwheel_refund_fixture import build_refund  # noqa: E402

from gauntlet.application.errors import ApplicationError  # noqa: E402
from gauntlet.application.gate import ApprovalScope, AuthenticatedReviewer  # noqa: E402
from gauntlet.application.gate.repair import diff_paths  # noqa: E402
from gauntlet.composition import (  # noqa: E402
    GateTarget,
    build_gate,
    build_repair,
    refund_verification_suite,
)
from gauntlet.contracts import ApprovalDecision  # noqa: E402
from gauntlet.domain import GateStatus  # noqa: E402
from gauntlet.settings import MissingSettingError, Settings  # noqa: E402


def _reviewer(settings: Settings) -> AuthenticatedReviewer:
    presented = os.environ.get("GAUNTLET_REVIEWER_TOKEN", "")
    reviewers = settings.integrations().reviewers
    if reviewers is None or not presented:
        raise MissingSettingError("GAUNTLET_REVIEWER_TOKENS", "GAUNTLET_REVIEWER_TOKEN")
    for name, token in reviewers.tokens:
        if hmac.compare_digest(token.reveal().encode(), presented.encode()):
            return AuthenticatedReviewer(reviewer_id=name, channel="api")
    raise PermissionError("reviewer token is not recognised")


async def run(args: argparse.Namespace) -> dict[str, object]:
    settings = Settings.from_env()
    repo = Path(tempfile.mkdtemp(prefix="gauntlet-repair-")) / "cartwheel"
    build_refund(repo)
    target = GateTarget.cartwheel_refund(repo)
    change = target.change(intent=str(target.manifest["change"]["feature_intent"]))
    output = ROOT / "artifacts" / "repair-runs" / args.run_id
    gate = await build_gate(
        settings, target, model="scripted", sandbox="fake", browser="fake",
        artifact_root=output / "evidence",
    )  # fmt: skip
    try:
        report = await gate.use_case.execute(args.run_id, change, target.fixture_checksum)
        confirmed = [
            o for o in report.outcomes if o.finding.status is GateStatus.CONFIRMED_REGRESSION
        ]
        if not confirmed:
            return {"status": "nothing_to_repair", "gate_status": report.overall.value}
        outcome = confirmed[0]
        repair = build_repair(settings, target, gate, model=args.model)
        plan, plan_hash = await repair.use_case.propose(
            args.run_id, outcome.finding, outcome.attack, change.head_sha
        )
        result: dict[str, object] = {
            "adapters": {**gate.labels, **repair.labels},
            "gate_status": report.overall.value,
            "finding_id": outcome.finding.finding_id,
            "fix_plan_id": plan.fix_plan_id,
            "plan_sha256": plan_hash,
            "allowed_paths": list(plan.allowed_paths),
            "touched_paths": list(diff_paths(plan.unified_diff)),
            "unified_diff": plan.unified_diff,
            "rationale": plan.rationale,
            "test_plan": list(plan.test_plan),
        }
        if args.approve_hash is None:
            result["status"] = "awaiting_human_approval"
            result["next"] = "re-run with --approve-hash <plan_sha256> and a reviewer token"
            return result
        reviewer = _reviewer(settings)
        approval = await repair.approvals.record(
            ApprovalScope(
                run_id=args.run_id,
                target_id=target.target_id,
                fixture_id=target.fixture_id,
                current_plan_sha256=plan_hash,
                allowed_paths=plan.allowed_paths,
            ),
            ApprovalDecision(
                subject="fix_plan",
                subject_id=plan.fix_plan_id,
                plan_sha256=args.approve_hash,
                decision="approved",
            ),
            reviewer,
        )
        repaired = await repair.use_case.execute(
            approval.approval_id,
            plan,
            target_id=target.target_id,
            fixture_id=target.fixture_id,
            fixture_checksum=target.fixture_checksum,
            suite=refund_verification_suite(target, outcome.attack),
        )
        result.update(
            {
                "status": "verified" if repaired.patched_sha else "not_applied",
                "approved_by": approval.reviewer_id,
                "approval_id": approval.approval_id,
                "patched_sha": repaired.patched_sha,
                "checks": [vars(c) for c in repaired.checks],
                "release_verdict": repaired.verdict.value,
                "note": repaired.note,
            }
        )
        return result
    finally:
        await gate.aclose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--model", choices=("scripted", "azure", "bedrock"), default="scripted")
    parser.add_argument("--approve-hash")
    args = parser.parse_args()
    try:
        result = asyncio.run(run(args))
    except (MissingSettingError, PermissionError, ValueError, ApplicationError) as exc:
        print(json.dumps({"status": "refused", "error": str(exc)}))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
