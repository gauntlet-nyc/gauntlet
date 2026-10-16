"""Run the Gate pipeline on the Cartwheel Help-button change. Defaults run fully offline.

    uv run python scripts/run_gate.py                       # scripted model, fake sandbox,
                                                            # simulated layout (offline)
    uv run python scripts/run_gate.py --clean               # unrelated change: expect passed
    uv run python scripts/run_gate.py --change refund-tool  # AI-agent attack, real tool code
    RUN_LIVE_INTEGRATIONS=1 uv run python scripts/run_gate.py --model azure
    RUN_LIVE_INTEGRATIONS=1 uv run --group live-providers python scripts/run_gate.py \
        --model azure --sandbox daytona --browser anchor
    CARTWHEEL_BASE_ORIGIN=http://127.0.0.1:3101 CARTWHEEL_HEAD_ORIGIN=http://127.0.0.1:3102 \
        uv run --group live-providers python scripts/run_gate.py --sandbox local --browser local

The report labels every adapter that ran. Offline labels mean no provider was contacted.
"""

import argparse
import asyncio
import json
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_cartwheel_clean_fixture import build_clean  # noqa: E402
from build_cartwheel_refund_fixture import build_refund  # noqa: E402

from gauntlet.composition import GateTarget, build_gate, readiness  # noqa: E402
from gauntlet.settings import MissingSettingError, Settings  # noqa: E402


async def run(args: argparse.Namespace) -> dict[str, object]:
    settings = Settings.from_env()
    workdir = Path(tempfile.mkdtemp(prefix="gauntlet-gate-"))
    repo = workdir / "cartwheel"
    if args.change == "refund-tool":
        if args.clean:
            raise ValueError("--clean applies to the help-button change only")
        refund = build_refund(repo)
        target = GateTarget.cartwheel_refund(repo)
        if (refund["refund_base_sha"], refund["refund_head_sha"]) != (
            target.base_sha,
            target.head_sha,
        ):
            raise RuntimeError("rebuilt refund fixture SHAs differ from the pinned manifest")
        intent = str(target.manifest["change"]["feature_intent"])
        built: dict[str, str] = {}
    else:
        built = build_clean(repo)
        target = GateTarget.cartwheel(repo)
        if (built["base_sha"], built["regression_head_sha"]) != (target.base_sha, target.head_sha):
            raise RuntimeError("rebuilt fixture SHAs differ from the pinned manifest")
        intent = "Add a floating Help button"
    if args.clean:
        target = replace(target, clean_head_sha=built["clean_sha"])
        intent = "Clarify the product description"
    change = target.change(intent=intent)
    run_id = args.run_id or f"gate-{uuid4().hex[:12]}"
    output = Path(args.output) if args.output else ROOT / "artifacts" / "gate-runs" / run_id
    runtime = await build_gate(
        settings,
        target,
        model=args.model,
        sandbox=args.sandbox,
        browser=args.browser,
        artifact_root=output / "evidence",
    )
    try:
        report = await runtime.use_case.execute(run_id, change, target.fixture_checksum)
    finally:
        await runtime.aclose()
    offline = all(
        runtime.labels[part].startswith("offline") for part in ("model", "sandbox", "browser")
    )
    return {
        "mode": "offline" if offline else "mixed_or_live",
        "adapters": runtime.labels,
        "live_readiness_missing": readiness(settings),
        "run_id": run_id,
        "comparison": "clean_unrelated_change" if args.clean else f"{args.change}_change",
        "base_sha": change.base_sha,
        "head_sha": change.head_sha,
        "plan_hash": report.plan.plan_hash,
        "plan_frozen_before_execution": report.events[1].event_type == "plan_frozen",
        "model_id": report.plan.model_id,
        "accepted_attacks": [a.attack_id for a in report.plan.attacks],
        "rejected_attacks": [
            {"attack_id": r.attack_id, "reasons": list(r.reasons)} for r in report.plan.rejected
        ],
        "overall_status": report.overall.value,
        "findings": [f.model_dump(mode="json") for f in report.findings],
        "events": [
            {"sequence": e.sequence, "type": e.event_type, "payload": e.payload}
            for e in report.events
        ],
        "evidence_dir": str(output / "evidence"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=("scripted", "azure", "bedrock"), default="scripted")
    parser.add_argument("--sandbox", choices=("fake", "local", "daytona"), default="fake")
    parser.add_argument("--browser", choices=("fake", "local", "anchor"), default="fake")
    parser.add_argument("--change", choices=("help-button", "refund-tool"), default="help-button")
    parser.add_argument("--clean", action="store_true", help="use the unrelated clean change")
    parser.add_argument("--run-id")
    parser.add_argument("--output")
    args = parser.parse_args()
    try:
        result = asyncio.run(run(args))
    except (MissingSettingError, ValueError, RuntimeError) as exc:
        print(json.dumps({"overall_status": "not_tested", "error": str(exc)}))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
