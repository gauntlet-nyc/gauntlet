"""Execute an independently checked frozen UI plan on one local synthetic revision."""

import argparse
import asyncio
import json
import subprocess
from pathlib import Path
from uuid import uuid4

from gauntlet.contracts import ChangeRequest, EvidenceSubject
from gauntlet.integrations.browser_evidence import BrowserEvidenceCollector
from gauntlet.integrations.fixture_identity import verify_fixture_build_receipt
from gauntlet.integrations.local_artifacts import LocalArtifactStore
from gauntlet.integrations.local_browser import LocalBrowserProvider
from gauntlet.planning import FrozenPlan
from gauntlet.ports.sandbox import EnvironmentHandle
from gauntlet.verification.registry import RegisteredOracleRegistry
from gauntlet.verification.stored_browser import StoredBrowserOracle
from gauntlet.workers.ui import UIWorker

ROOT = Path(__file__).resolve().parents[1]


async def run_attacks(
    frozen: FrozenPlan,
    environment: EnvironmentHandle,
    worker: UIWorker,
    oracle: StoredBrowserOracle,
) -> list[dict[str, object]]:
    observations: list[dict[str, object]] = []
    for attack in frozen.attacks:
        for _ in range(2):
            subject = EvidenceSubject(
                run_id=frozen.run_id,
                attempt_id=f"local-attempt-{uuid4().hex}",
                observation_id=f"local-observation-{uuid4().hex}",
                environment_id=environment.environment_id,
                source_sha=environment.source_sha,
                fixture_checksum=environment.fixture_checksum,
                collector="browser_collector",
            )
            observation = await worker.run(attack, environment, subject)
            verdicts = [
                (await oracle.evaluate(oracle_id, attack, observation, subject)).model_dump(
                    mode="json"
                )
                for oracle_id in attack.oracle_ids
            ]
            observations.append(
                {
                    "attack_id": attack.attack_id,
                    "subject": subject.model_dump(mode="json"),
                    "observation": observation.model_dump(mode="json"),
                    "verdicts": verdicts,
                }
            )
    return observations


async def probe(
    frozen: FrozenPlan, revision: str, origin: str, chrome: Path, fixture_repo: Path, output: Path
) -> dict[str, object]:
    from gauntlet.planning import require_executable_plan

    require_executable_plan(frozen)
    if revision not in {"base", "head"}:
        raise ValueError("revision must be base or head")
    if any(attack.worker_kind != "ui" for attack in frozen.attacks):
        raise ValueError("local consumer accepts UI attacks only")
    manifest = json.loads((ROOT / "apps/cartwheel/fixture-manifest.v1.json").read_text())
    change = frozen.change
    if (
        change.target_id != manifest["target_id"]
        or change.fixture_id != manifest["fixture_id"]
        or change.base_sha != manifest["git_refs"]["base_sha"]
        or change.head_sha != manifest["git_refs"]["head_sha"]
    ):
        raise ValueError("frozen change does not match the registered synthetic fixture")
    execute_sha = change.base_sha if revision == "base" else change.head_sha
    checkout = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=fixture_repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    if checkout != execute_sha:
        raise ValueError("fixture checkout differs from selected revision")
    await verify_fixture_build_receipt(origin, execute_sha)
    output.mkdir(parents=True, exist_ok=False)
    store = LocalArtifactStore(output / "artifacts")
    targets = {change.target_id: "checkout-primary-action"}
    registry = RegisteredOracleRegistry(plans=frozen.attacks, primary_targets=targets, evidence=())
    oracle = StoredBrowserOracle(store, primary_targets=targets)
    environment = EnvironmentHandle(
        environment_id=f"local-environment-{uuid4().hex}",
        target_id=change.target_id,
        source_sha=execute_sha,
        fixture_id=change.fixture_id,
        fixture_checksum=manifest["fixture_checksum_sha256"],
        preview_origin=origin,
    )
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(executable_path=str(chrome), headless=True)
        try:
            worker = UIWorker(
                LocalBrowserProvider(browser, BrowserEvidenceCollector(store)), registry
            )
            observations = await run_attacks(frozen, environment, worker, oracle)
        finally:
            await browser.close()
    report: dict[str, object] = {
        "mode": "frozen_local_ui_execution",
        "gate_status": "not_tested",
        "plan_hash": frozen.plan_hash,
        "run_id": frozen.run_id,
        "model_id": frozen.model_id,
        "revision": revision,
        "execute_sha": execute_sha,
        "fixture_build_receipt_verified": True,
        "server_source_verified": False,
        "attempts_per_attack": 2,
        "observations": observations,
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("revision", choices=("base", "head"))
    for name in ("receipt", "expected-change", "chrome", "fixture-repo", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    for name in (
        "expected-plan-hash",
        "expected-model-id",
        "expected-prompt-sha256",
        "expected-run-id",
        "origin",
    ):
        parser.add_argument(f"--{name}", required=True)
    args = parser.parse_args()
    try:
        from gauntlet.planning import load_frozen_plan

        with args.receipt.open("rb") as stream:
            raw = stream.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("receipt exceeds input limit")
        frozen = load_frozen_plan(
            raw.decode("utf-8"),
            expected_change=ChangeRequest.model_validate_json(args.expected_change.read_text()),
            expected_plan_hash=args.expected_plan_hash,
            expected_model_id=args.expected_model_id,
            expected_prompt_sha256=args.expected_prompt_sha256,
            expected_run_id=args.expected_run_id,
        )
        result = asyncio.run(
            probe(frozen, args.revision, args.origin, args.chrome, args.fixture_repo, args.output)
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "environment_error",
                    "gate_status": "not_tested",
                    "error_type": type(exc).__name__,
                }
            )
        )
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
