"""Opt-in planning probe (Bedrock, or Azure OpenAI as a dev stand-in); executes no attacks."""

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from gauntlet.analysis import GitRepositoryInspector
from gauntlet.application.gate import (
    PlanChangeDependencies,
    PlanChangeUseCase,
    StaticTargetCatalog,
    profile_from_manifest,
)
from gauntlet.contracts import ChangeRequest, RunEvent
from gauntlet.integrations.azure_openai import create_azure_openai_gateway
from gauntlet.integrations.bedrock import create_bedrock_gateway
from gauntlet.integrations.fake.storage import FakeRunStore
from gauntlet.planning import AttackPlanner, FrozenPlan, PlanningLimits, serialize_frozen_plan
from gauntlet.ports import TargetCatalog
from gauntlet.ports.errors import EnvironmentUnavailableError
from gauntlet.ports.model import ModelGateway
from gauntlet.settings import Settings, SettingsError
from gauntlet.verification.registry import RegisteredOracleRegistry

ROOT = Path(__file__).resolve().parents[1]
INSTRUCTIONS = ROOT / "docs/prompts/p1-ui-planner.md"
MANIFEST = ROOT / "apps/cartwheel/fixture-manifest.v1.json"
AZURE_SETTINGS = ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT", "AZURE_OPENAI_API_KEY")
PINNED_BOTO3 = "1.43.114"


def _owns_reservation(path: Path, descriptor: int) -> bool:
    try:
        current = os.stat(path, follow_symlinks=False)
        reserved = os.fstat(descriptor)
    except OSError:
        return False
    return (current.st_dev, current.st_ino) == (reserved.st_dev, reserved.st_ino)


def _release_reservation(path: Path, descriptor: int, *, published: bool) -> None:
    try:
        if not published and _owns_reservation(path, descriptor):
            path.unlink()
    finally:
        os.close(descriptor)


async def freeze_live_plan(
    repository: Path,
    change: ChangeRequest,
    gateway: ModelGateway,
    instructions: str,
    targets: TargetCatalog,
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
            targets=targets,
            clock=lambda: datetime.now(UTC),
            new_event_id=lambda: f"event-{uuid4().hex}",
        )
    )
    frozen = await use_case.execute(run_id, change)
    return frozen, await store.list_events(run_id)


def _cartwheel_catalog() -> StaticTargetCatalog:
    """The only authorized target is the committed synthetic Cartwheel manifest."""
    manifest = json.loads(MANIFEST.read_text())
    return StaticTargetCatalog(profile_from_manifest(manifest))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("bedrock", "azure"), default="bedrock")
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
        "--output": args.output is not None,
        "unused --output": args.output is None or not os.path.lexists(args.output),
    }
    reasoning_model = False
    if args.provider == "bedrock":
        try:
            reasoning_model = Settings.from_env(
                {"BEDROCK_REASONING_MODEL": os.environ.get("BEDROCK_REASONING_MODEL", "0")}
            ).flag("BEDROCK_REASONING_MODEL")
        except SettingsError:
            required["valid BEDROCK_REASONING_MODEL"] = False
        required.update(
            {
                "--model-id": bool(args.model_id),
                "--region": bool(args.region),
                f"boto3=={PINNED_BOTO3}": sdk_version == PINNED_BOTO3,
            }
        )
    else:
        required.update(
            {
                key: bool(os.environ.get(key, "").strip())
                and "REPLACE_" not in os.environ.get(key, "")
                for key in AZURE_SETTINGS
            }
        )
    missing = [name for name, ready in required.items() if not ready]
    report: dict[str, object] = {
        "mode": f"{args.provider}_plan_freeze_only",
        "provider": args.provider,
        "sponsor_evidence": args.provider == "bedrock",
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
    try:
        change = ChangeRequest.model_validate_json(args.change_request.read_text())
    except Exception as exc:
        report.update(status="environment_error", missing=[], error_type=type(exc).__name__)
        print(json.dumps(report, sort_keys=True))
        return 1
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        reservation = os.open(
            args.output,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except OSError as exc:
        report.update(missing=["usable --output"], error_type=type(exc).__name__)
        print(json.dumps(report, sort_keys=True))
        return 2
    gateway = None
    error_type: str | None = None
    try:
        gateway = (
            create_bedrock_gateway(
                model_id=args.model_id,
                region=args.region,
                reasoning_model=reasoning_model,
            )
            if args.provider == "bedrock"
            else create_azure_openai_gateway(os.environ)
        )
        instructions = INSTRUCTIONS.read_text()
        frozen, events = asyncio.run(
            freeze_live_plan(args.repository, change, gateway, instructions, _cartwheel_catalog())
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
        _release_reservation(args.output, reservation, published=False)
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
    published = False
    temp_path: Path | None = None
    try:
        report["frozen_plan"] = json.loads(
            serialize_frozen_plan(
                frozen, prompt_sha256=hashlib.sha256(instructions.encode("utf-8")).hexdigest()
            )
        )
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=args.output.parent, delete=False
        ) as temp:
            temp_path = Path(temp.name)
            json.dump(report, temp, indent=2, sort_keys=True)
            temp.write("\n")
        if not _owns_reservation(args.output, reservation):
            raise OSError("output reservation changed before publication")
        os.replace(temp_path, args.output)
        published = True
    except Exception as exc:
        report.update(status="environment_error", error_type=type(exc).__name__)
        print(
            json.dumps(
                {
                    key: value
                    for key, value in report.items()
                    if key not in {"attacks", "frozen_plan"}
                }
            )
        )
        return 1
    finally:
        try:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
        finally:
            _release_reservation(args.output, reservation, published=published)
    print(
        json.dumps(
            {key: value for key, value in report.items() if key not in {"attacks", "frozen_plan"}},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
