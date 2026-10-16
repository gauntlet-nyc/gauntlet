"""Opt-in Daytona snapshot restore smoke; no browser or Gate verdict.

Checks registered checkout/state and synthetic compiled-build receipts. Success
is not image attestation or proof of mutable runtime state. Signed preview URLs
and provider exception messages never enter the report.
"""

import argparse
import asyncio
import importlib.metadata
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

import httpx

from gauntlet.contracts import ChangeRequest
from gauntlet.execution.environment_pair import gate_environment_pair
from gauntlet.execution.provider_smoke_cleanup import finish_smoke_resources
from gauntlet.execution.provider_smoke_config import load_registration
from gauntlet.integrations.daytona.provider import (
    DaytonaRuntime,
    DaytonaSandboxProvider,
    HealthProbe,
    RegisteredTarget,
)
from gauntlet.integrations.daytona.sdk import HttpxHealthProbe, SdkDaytonaRuntime
from gauntlet.integrations.fixture_identity import verify_hosted_fixture_build_receipt

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "apps/cartwheel/fixture-manifest.v1.json"
PINNED_DAYTONA = "0.224.1"


class RestoreRuntime(DaytonaRuntime, Protocol):
    async def close(self) -> None: ...


def preflight(
    environment: Mapping[str, str], *, spend_authorized: bool, registration_present: bool
) -> list[str]:
    missing = []
    if environment.get("RUN_LIVE_INTEGRATIONS") != "1":
        missing.append("live_opt_in")
    if not spend_authorized:
        missing.append("spend_authorization")
    if not registration_present:
        missing.append("registration")
    if "cartwheel-fixture" not in {
        item.strip() for item in environment.get("GAUNTLET_ALLOWED_TARGET_IDS", "").split(",")
    }:
        missing.append("cartwheel_target_allowlist")
    for name in ("DAYTONA_API_KEY", "DAYTONA_API_URL", "DAYTONA_TARGET"):
        value = environment.get(name, "").strip()
        if not value or value.upper().startswith("REPLACE_"):
            missing.append(name)
    return missing


async def restore_pair(
    runtime: RestoreRuntime,
    change: ChangeRequest,
    target: RegisteredTarget,
    *,
    health: HealthProbe,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, object]:
    """Own cleanup of the supplied runtime and every sandbox created by this call."""
    sandbox: DaytonaSandboxProvider | None = None
    restored: list[dict[str, str]] = []
    error_type: str | None = None
    try:
        sandbox = DaytonaSandboxProvider(runtime, {target.target_id: target}, health)
        async with gate_environment_pair(sandbox, change, target.fixture_checksum) as pair:
            for environment in (pair.base, pair.head):
                await verify_hosted_fixture_build_receipt(
                    environment.preview_origin,
                    environment.source_sha,
                    preview_domain_suffix=target.preview_domain_suffix,
                    transport=transport,
                )
                restored.append(
                    {
                        "environment_id": environment.environment_id,
                        "source_sha": environment.source_sha,
                    }
                )
    except (Exception, asyncio.CancelledError) as exc:
        error_type = type(exc).__name__
    finally:
        cleanup = await finish_smoke_resources(None, sandbox, None, runtime)
    pending = sandbox.pending_cleanup_ids if sandbox is not None else ()
    success = (
        len(restored) == 2
        and error_type is None
        and not cleanup.errors
        and not cleanup.cancelled
        and not pending
    )
    return {
        "mode": "daytona_snapshot_restore_only",
        "status": "passed" if success else "environment_error",
        "gate_status": "not_tested",
        "target_id": target.target_id,
        "base_sha": change.base_sha,
        "head_sha": change.head_sha,
        "fixture_checksum": target.fixture_checksum,
        "restored": restored,
        "synthetic_build_receipt_verified": len(restored) == 2,
        "sandbox_image_attested": False,
        "error_type": error_type,
        "cleanup_errors": cleanup.errors,
        "cancelled_during_cleanup": cleanup.cancelled,
        "pending_sandbox_cleanup_ids": pending,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registration", type=Path)
    parser.add_argument("--output", type=Path, help="New directory for sanitized report.json")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--authorize-spend", action="store_true")
    args = parser.parse_args(argv)
    missing = preflight(
        os.environ,
        spend_authorized=args.authorize_spend,
        registration_present=args.registration is not None and args.registration.is_file(),
    )
    try:
        version = importlib.metadata.version("daytona")
    except importlib.metadata.PackageNotFoundError:
        version = None
    if version != PINNED_DAYTONA:
        missing.append("daytona==" + PINNED_DAYTONA)
    if args.output is None:
        missing.append("output")
    if not args.execute or missing:
        print(
            json.dumps(
                {
                    "scope": "local_prerequisites_only",
                    "status": "not_tested",
                    "gate_status": "not_tested",
                    "missing": missing,
                    "sdk_version": version,
                }
            )
        )
        return 2 if args.execute and missing else 0
    assert args.registration is not None and args.output is not None
    try:
        change, target = load_registration(args.registration, json.loads(MANIFEST.read_text()))
        args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(
            json.dumps(
                {
                    "status": "not_tested",
                    "gate_status": "not_tested",
                    "error_type": type(exc).__name__,
                }
            )
        )
        return 2
    try:
        runtime = SdkDaytonaRuntime.from_credentials(
            api_key=os.environ["DAYTONA_API_KEY"],
            api_url=os.environ["DAYTONA_API_URL"],
            target=os.environ["DAYTONA_TARGET"],
        )
        result = asyncio.run(restore_pair(runtime, change, target, health=HttpxHealthProbe()))
    except (Exception, asyncio.CancelledError) as exc:
        result = {
            "mode": "daytona_snapshot_restore_only",
            "status": "environment_error",
            "gate_status": "not_tested",
            "error_type": type(exc).__name__,
        }
    result["sdk_version"] = version
    try:
        (args.output / "report.json").write_text(json.dumps(result, indent=2) + "\n")
    except OSError:
        result.update(status="environment_error", report_write_failed=True)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
