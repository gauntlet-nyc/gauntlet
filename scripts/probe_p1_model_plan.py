"""Opt-in Bedrock planning probe; freezes a plan but executes no attacks."""

import argparse
import asyncio
import importlib.metadata
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from gauntlet.analysis import GitRepositoryInspector
from gauntlet.application.gate import PlanChangeDependencies, PlanChangeUseCase
from gauntlet.contracts import ChangeRequest, RunEvent
from gauntlet.integrations.bedrock import create_bedrock_gateway
from gauntlet.integrations.fake.storage import FakeRunStore
from gauntlet.planning import AttackPlanner, FrozenPlan, PlanningLimits
from gauntlet.ports.errors import EnvironmentUnavailableError
from gauntlet.ports.model import ModelGateway
from gauntlet.verification.registry import RegisteredOracleRegistry

ROOT = Path(__file__).resolve().parents[1]
INSTRUCTIONS = ROOT / "docs/prompts/p1-ui-planner.md"
PINNED_BOTO3 = "1.43.114"


async def freeze_live_plan(
    repository: Path, change: ChangeRequest, gateway: ModelGateway, instructions: str
) -> tuple[FrozenPlan, tuple[RunEvent, ...]]:
    """Use the existing diff inspector, validator and event freeze with a supplied model port."""
    store = FakeRunStore(initial_sequence=0)
    run_id = f"model-plan-{uuid4().hex}"
    use_case = PlanChangeUseCase(
        PlanChangeDependencies(
            inspector=GitRepositoryInspector({change.repository_id: repository}),
            planner=AttackPlanner(
                gateway,
                RegisteredOracleRegistry(plans=(), primary_targets={}, evidence=()),
                instructions,
                PlanningLimits(),
            ),
            store=store,
            clock=lambda: datetime.now(UTC),
            new_event_id=lambda: f"event-{uuid4().hex}",
        )
    )
    frozen = await use_case.execute(run_id, change)
    return frozen, await store.list_events(run_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path)
    parser.add_argument("--change-request", type=Path)
    parser.add_argument("--model-id")
    parser.add_argument("--region")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--authorize-spend", action="store_true")
    args = parser.parse_args(argv)
    try:
        sdk_version = importlib.metadata.version("boto3")
    except importlib.metadata.PackageNotFoundError:
        sdk_version = None
    required = {
        "--execute": args.execute,
        "--authorize-spend": args.authorize_spend,
        "RUN_LIVE_INTEGRATIONS=1": os.environ.get("RUN_LIVE_INTEGRATIONS") == "1",
        "--repository": args.repository is not None,
        "--change-request": args.change_request is not None,
        "--model-id": bool(args.model_id),
        "--region": bool(args.region),
        "--output": args.output is not None,
        "unused --output": args.output is None or not args.output.exists(),
        f"boto3=={PINNED_BOTO3}": sdk_version == PINNED_BOTO3,
    }
    missing = [name for name, ready in required.items() if not ready]
    report: dict[str, object] = {
        "mode": "bedrock_plan_freeze_only",
        "status": "not_tested",
        "gate_status": "not_tested",
        "plan_hash": None,
        "sdk_version": sdk_version,
        "missing": missing,
    }
    if missing:
        print(json.dumps(report, sort_keys=True))
        return 2
    assert args.repository is not None
    assert args.change_request is not None
    assert args.output is not None
    gateway = None
    error_type: str | None = None
    try:
        change = ChangeRequest.model_validate_json(args.change_request.read_text())
        gateway = create_bedrock_gateway(model_id=args.model_id, region=args.region)
        frozen, events = asyncio.run(
            freeze_live_plan(args.repository, change, gateway, INSTRUCTIONS.read_text())
        )
    except Exception as exc:
        error_type = type(exc).__name__
    finally:
        if gateway is not None:
            try:
                gateway.close()
            except EnvironmentUnavailableError:
                error_type = "EnvironmentUnavailableError"
    if error_type is not None:
        report.update(status="environment_error", missing=[], error_type=error_type)
        print(json.dumps(report, sort_keys=True))
        return 1
    status = "accepted" if frozen.attacks else "rejected" if frozen.rejected else "not_tested"
    report.update(
        status=status,
        missing=[],
        plan_hash=frozen.plan_hash,
        run_id=frozen.run_id,
        planner_version=frozen.planner_version,
        model_id=frozen.model_id,
        frozen_at=frozen.frozen_at.isoformat(),
        change=frozen.change.model_dump(mode="json"),
        impact=frozen.impact.model_dump(mode="json"),
        accepted_attacks=len(frozen.attacks),
        rejected_attacks=len(frozen.rejected),
        not_tested_reason=frozen.not_tested_reason,
        attacks=[attack.model_dump(mode="json") for attack in frozen.attacks],
        events=[
            {"type": event.event_type, "sequence": event.sequence, "trace_id": event.trace_id}
            for event in events
        ],
    )
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=args.output.parent, delete=False
        ) as temp:
            json.dump(report, temp, indent=2, sort_keys=True)
            temp.write("\n")
            temp_path = Path(temp.name)
        try:
            os.link(temp_path, args.output)
        finally:
            temp_path.unlink(missing_ok=True)
    except OSError as exc:
        report.update(status="environment_error", error_type=type(exc).__name__)
        print(json.dumps({key: value for key, value in report.items() if key != "attacks"}))
        return 1
    print(
        json.dumps(
            {key: value for key, value in report.items() if key != "attacks"}, sort_keys=True
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
