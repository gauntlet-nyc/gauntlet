"""B-01 Daytona/Anchor connectivity smoke for owned synthetic Cartwheel only.

Preflight makes no paid calls. --execute requires explicit spend opt-in and
operator snapshot registration. A successful screenshot smoke is not a Gate
regression verdict: the synthetic build receipt does not attest the sandbox
image, and proxy policy remains unverified.
"""

import argparse
import asyncio
import importlib.metadata
import json
import os
from pathlib import Path

from gauntlet.execution.provider_smoke import capture_provider_pair
from gauntlet.execution.provider_smoke_cleanup import finish_smoke_resources
from gauntlet.execution.provider_smoke_config import load_registration, preflight
from gauntlet.integrations.anchor.provider import AnchorBrowserProvider
from gauntlet.integrations.anchor.sdk import SdkAnchorRuntime
from gauntlet.integrations.browser_evidence import BrowserEvidenceCollector
from gauntlet.integrations.daytona.provider import DaytonaSandboxProvider
from gauntlet.integrations.daytona.sdk import HttpxHealthProbe, SdkDaytonaRuntime
from gauntlet.integrations.local_artifacts import LocalArtifactStore

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "apps/cartwheel/fixture-manifest.v1.json"
PINNED_SDKS = {"daytona": "0.224.1", "anchorbrowser": "1.0.1", "playwright": "1.64.0"}


def _sdk_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for package in PINNED_SDKS:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return versions


async def _live_capture(registration: Path, output: Path) -> dict[str, object]:
    manifest = json.loads(MANIFEST.read_text())
    change, target = load_registration(registration, manifest)
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    artifacts = LocalArtifactStore(output / "artifacts")
    daytona: SdkDaytonaRuntime | None = None
    anchor: SdkAnchorRuntime | None = None
    sandbox: DaytonaSandboxProvider | None = None
    browser: AnchorBrowserProvider | None = None
    captures: list[dict[str, str]] = []
    error_type: str | None = None
    try:
        daytona = SdkDaytonaRuntime.from_credentials(
            api_key=os.environ["DAYTONA_API_KEY"],
            api_url=os.environ["DAYTONA_API_URL"],
            target=os.environ["DAYTONA_TARGET"],
        )
        anchor = SdkAnchorRuntime.from_credentials(
            api_key=os.environ["ANCHOR_API_KEY"],
            proxy_server=os.environ["ANCHOR_PROXY_SERVER"],
            proxy_username=os.environ["ANCHOR_PROXY_USERNAME"],
            proxy_password=os.environ["ANCHOR_PROXY_PASSWORD"],
        )
        sandbox = DaytonaSandboxProvider(daytona, {target.target_id: target}, HttpxHealthProbe())
        browser = AnchorBrowserProvider(
            anchor,
            BrowserEvidenceCollector(artifacts),
            preview_domain_suffix=target.preview_domain_suffix,
        )
        results = await capture_provider_pair(
            sandbox,
            browser,
            artifacts,
            change,
            target.fixture_checksum,
            ready_path=target.ready_path,
            registered_target=target,
        )
        captures = [vars(result) for result in results]
    except (Exception, asyncio.CancelledError) as exc:
        # Provider messages can contain signed preview tokens or credentials.
        error_type = type(exc).__name__
    finally:
        cleanup = await finish_smoke_resources(browser, sandbox, anchor, daytona)
    status = (
        "passed"
        if captures and error_type is None and not cleanup.errors and not cleanup.cancelled
        else "environment_error"
    )
    report: dict[str, object] = {
        "mode": "live_provider_smoke_only",
        "status": status,
        "gate_status": "not_tested",
        "synthetic_build_receipt_verified": status == "passed",
        "sandbox_image_attested": False,
        "egress_proxy_policy_verified": False,
        "sdk_versions": _sdk_versions(),
        "target_id": target.target_id,
        "base_sha": change.base_sha,
        "head_sha": change.head_sha,
        "fixture_checksum": target.fixture_checksum,
        "captures": captures,
        "error_type": error_type,
        "cleanup_errors": cleanup.errors,
        "cancelled_during_cleanup": cleanup.cancelled,
        "pending_browser_cleanup_ids": browser.pending_cleanup_ids if browser is not None else (),
        "pending_sandbox_cleanup_ids": sandbox.pending_cleanup_ids if sandbox is not None else (),
        "pending_anchor_cleanup_ids": anchor.pending_cleanup_ids if anchor is not None else (),
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registration", type=Path)
    parser.add_argument("--output", type=Path, default=Path("/tmp/gauntlet-b01-live-smoke"))
    parser.add_argument("--execute", action="store_true", help="Create paid provider resources")
    parser.add_argument("--authorize-spend", action="store_true")
    args = parser.parse_args()
    report = preflight(
        os.environ,
        spend_authorized=args.authorize_spend,
        registration_present=args.registration is not None and args.registration.is_file(),
    )
    versions = _sdk_versions()
    report["sdk_versions"] = versions
    if versions != PINNED_SDKS:
        missing = report["missing"]
        assert isinstance(missing, list)
        missing.append("pinned_provider_sdks")
    if not args.execute or report["missing"]:
        print(json.dumps(report, indent=2))
        raise SystemExit(2 if args.execute and report["missing"] else 0)
    assert args.registration is not None
    try:
        load_registration(args.registration, json.loads(MANIFEST.read_text()))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(
            json.dumps(
                {
                    "scope": "local_prerequisites_only",
                    "status": "not_tested",
                    "missing": ["valid_registration"],
                    "error_type": type(exc).__name__,
                },
                indent=2,
            )
        )
        raise SystemExit(2) from None
    result = asyncio.run(_live_capture(args.registration, args.output))
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
