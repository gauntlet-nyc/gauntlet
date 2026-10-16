"""Freeze a diff-cited scripted UI plan and run it in local headless Chrome.

This is an offline diagnostic. The operator selects and builds the synthetic
checkout; this script verifies its checkout SHA and the trusted fixture's
compiled build receipt before browser actions. The receipt does not attest a
hostile target's running source. No model or cloud provider is called.
"""

import argparse
import asyncio
import hashlib
import json
import subprocess
from pathlib import Path
from typing import cast
from uuid import uuid4

from gauntlet.application.gate import StaticTargetCatalog, profile_from_manifest
from gauntlet.contracts import ChangeRequest, EvidenceSubject
from gauntlet.integrations.browser_evidence import BrowserEvidenceCollector
from gauntlet.integrations.fixture_identity import verify_fixture_build_receipt
from gauntlet.integrations.local_artifacts import LocalArtifactStore
from gauntlet.integrations.local_browser import LocalBrowserProvider, PlaywrightBrowser
from gauntlet.integrations.local_gate_diagnostic import freeze_diagnostic_plan
from gauntlet.ports.sandbox import EnvironmentHandle
from gauntlet.verification.registry import RegisteredOracleRegistry
from gauntlet.verification.stored_browser import StoredBrowserOracle
from gauntlet.workers.ui import UIWorker


def _checkout_sha(repo: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


async def probe(
    scenario: str,
    origin: str,
    chrome: Path,
    fixture_repo: Path,
    output: Path,
    *,
    clean_sha: str | None = None,
    attempts: int = 2,
    run_id: str | None = None,
) -> dict[str, object]:
    if not 1 <= attempts <= 5:
        raise ValueError("local diagnostic attempts must be between 1 and 5")
    if scenario == "clean" and clean_sha is None:
        raise ValueError("clean scenario requires its synthetic commit SHA")
    if scenario == "head" and clean_sha is not None:
        raise ValueError("head scenario cannot use a clean commit SHA")
    manifest = json.loads(Path("apps/cartwheel/fixture-manifest.v1.json").read_text())
    base_sha = manifest["git_refs"]["base_sha"]
    head_sha = clean_sha if clean_sha is not None else manifest["git_refs"]["head_sha"]
    execute_sha = base_sha if scenario == "base" else head_sha
    if _checkout_sha(fixture_repo) != execute_sha:
        raise ValueError("fixture checkout is not at the selected execution revision")
    await verify_fixture_build_receipt(origin, execute_sha)
    change = ChangeRequest(
        repository_id="cartwheel",
        base_sha=base_sha,
        head_sha=head_sha,
        fixture_id=manifest["fixture_id"],
        target_id=manifest["target_id"],
        max_cost_usd_cents=500,
        feature_intent=(
            "Clarify the product description" if clean_sha is not None else "Synthetic UI update"
        ),
    )
    frozen_result = await freeze_diagnostic_plan(
        fixture_repo,
        change,
        targets=StaticTargetCatalog(profile_from_manifest(manifest)),
        run_id=run_id,
    )
    frozen = frozen_result.frozen
    if (
        len(frozen.attacks) != 1
        or frozen.rejected
        or [event.event_type for event in frozen_result.events] != ["impact_mapped", "plan_frozen"]
        or frozen_result.events[-1].payload["plan_hash"] != frozen.plan_hash
    ):
        raise RuntimeError("local diagnostic did not freeze one validated attack")
    output.mkdir(parents=True, exist_ok=False)
    store = LocalArtifactStore(output / "artifacts")
    oracles = RegisteredOracleRegistry(
        plans=frozen.attacks,
        primary_targets={change.target_id: "checkout-primary-action"},
        evidence=(),
    )
    saved_oracle = StoredBrowserOracle(
        store, primary_targets={change.target_id: "checkout-primary-action"}
    )
    observations: list[dict[str, object]] = []
    typed_attempts: list[dict[str, object]] = []
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(executable_path=str(chrome), headless=True)
        try:
            worker = UIWorker(
                LocalBrowserProvider(
                    cast(PlaywrightBrowser, browser), BrowserEvidenceCollector(store)
                ),
                oracles,
            )
            for _ in range(attempts):
                subject = EvidenceSubject(
                    run_id=frozen.run_id,
                    attempt_id=f"local-attempt-{uuid4().hex}",
                    observation_id=f"local-observation-{uuid4().hex}",
                    environment_id=f"local-environment-{uuid4().hex}",
                    source_sha=execute_sha,
                    fixture_checksum=manifest["fixture_checksum_sha256"],
                    collector="browser_collector",
                )
                environment = EnvironmentHandle(
                    environment_id=subject.environment_id,
                    target_id=change.target_id,
                    source_sha=execute_sha,
                    fixture_id=change.fixture_id,
                    fixture_checksum=subject.fixture_checksum,
                    preview_origin=origin,
                )
                observation = await worker.run(frozen.attacks[0], environment, subject)
                verdict = await saved_oracle.evaluate(
                    "ui.primary_action_reachable", frozen.attacks[0], observation, subject
                )
                observations.append(
                    {
                        "observation_id": observation.observation_id,
                        "attempt_id": subject.attempt_id,
                        "source_sha": observation.source_sha,
                        "status": observation.status,
                        "action_outcomes": [record.outcome for record in observation.action_log],
                        "oracle_outcome": verdict.outcome,
                        "oracle_evidence_ids": verdict.evidence_ids,
                        "evidence_ids": observation.evidence_ids,
                    }
                )
                typed_attempts.append(
                    {
                        "subject": subject.model_dump(mode="json"),
                        "observation": observation.model_dump(mode="json"),
                        "verdicts": [verdict.model_dump(mode="json")],
                        "artifact_ids": list(observation.evidence_ids),
                    }
                )
        finally:
            await browser.close()
    report: dict[str, object] = {
        "mode": "scripted_local_p1_diagnostic",
        "scenario": scenario,
        "plan_source": "scripted_proposal_validated_against_real_diff",
        "plan_hash": frozen.plan_hash,
        "run_id": frozen.run_id,
        "plan_frozen_before_execution": True,
        "model_id": frozen.model_id,
        "change_base_sha": base_sha,
        "change_head_sha": head_sha,
        "execute_sha": execute_sha,
        "fixture_checksum": manifest["fixture_checksum_sha256"],
        "fixture_checkout_verified": True,
        "fixture_build_receipt_verified": True,
        "server_source_verified": False,
        "changed_files": frozen.impact.changed_files,
        "coverage_gaps": frozen.impact.coverage_gaps,
        "attack_source_refs": [
            ref.model_dump(mode="json") for ref in frozen.attacks[0].source_refs
        ],
        "observations": observations,
        "typed_attempts": typed_attempts,
    }
    report_bytes = (json.dumps(report, indent=2) + "\n").encode("utf-8")
    (output / "report.json").write_bytes(report_bytes)
    report["report_sha256"] = hashlib.sha256(report_bytes).hexdigest()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=("base", "head", "clean"))
    parser.add_argument("--origin", required=True)
    parser.add_argument("--chrome", type=Path, required=True)
    parser.add_argument("--fixture-repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--clean-sha")
    parser.add_argument("--attempts", type=int, default=2)
    parser.add_argument("--run-id")
    args = parser.parse_args()
    print(
        json.dumps(
            asyncio.run(
                probe(
                    args.scenario,
                    args.origin,
                    args.chrome,
                    args.fixture_repo,
                    args.output,
                    clean_sha=args.clean_sha,
                    attempts=args.attempts,
                    run_id=args.run_id,
                )
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
