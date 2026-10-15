"""Run the local browser port on a built, synthetic Cartwheel checkout.

This is a loopback diagnostic, not an Anchor/Daytona or hard-oracle run.
The checkout SHA is verified; the running server's source SHA is not.
"""

import argparse
import asyncio
import json
import subprocess
from pathlib import Path
from uuid import uuid4

from playwright.async_api import async_playwright

from gauntlet.application.evidence import check_evidence
from gauntlet.contracts import (
    AttackSpec,
    CaptureStep,
    ClickStep,
    EvidenceSubject,
    InspectStep,
    NavigateStep,
    Observation,
    ResizeStep,
)
from gauntlet.integrations.browser_evidence import BrowserEvidenceCollector
from gauntlet.integrations.local_artifacts import LocalArtifactStore
from gauntlet.integrations.local_browser import LocalBrowserProvider
from gauntlet.ports.sandbox import EnvironmentHandle
from gauntlet.verification.stored_browser import StoredBrowserOracle


async def probe(
    variant: str, origin: str, chrome: Path, fixture_repo: Path, output: Path
) -> dict[str, object]:
    manifest = json.loads(Path("apps/cartwheel/fixture-manifest.v1.json").read_text())
    source_sha = manifest["git_refs"][f"{variant}_sha"]
    checkout_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=fixture_repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if checkout_sha != source_sha:
        raise ValueError("fixture checkout is not at the manifest's selected revision")
    output.mkdir(parents=True, exist_ok=True)
    store = LocalArtifactStore(output / "artifacts")
    subject = EvidenceSubject(
        run_id=f"local-run-{uuid4().hex}",
        attempt_id=f"local-attempt-{uuid4().hex}",
        observation_id=f"local-observation-{uuid4().hex}",
        environment_id=f"local-environment-{uuid4().hex}",
        source_sha=source_sha,
        fixture_checksum=manifest["fixture_checksum_sha256"],
        collector="browser_collector",
    )
    environment = EnvironmentHandle(
        environment_id=subject.environment_id,
        target_id="cartwheel",
        source_sha=source_sha,
        fixture_id=manifest["fixture_id"],
        fixture_checksum=subject.fixture_checksum,
        preview_origin=origin,
    )
    steps = (
        NavigateStep(path="/checkout"),
        ResizeStep(width=375, height=812),
        InspectStep(target="checkout-primary-action"),
        ClickStep(target="checkout-primary-action"),
        CaptureStep(),
    )
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(executable_path=str(chrome), headless=True)
        try:
            adapter = LocalBrowserProvider(browser, BrowserEvidenceCollector(store))
            session = await adapter.open_session(environment, subject)
            try:
                records = [
                    await adapter.perform(session, index, step) for index, step in enumerate(steps)
                ]
            finally:
                await adapter.close_session(session)
        finally:
            await browser.close()
    expected = "ok" if variant == "base" else "blocked"
    if [record.outcome for record in records] != ["ok", "ok", "ok", expected, "ok"]:
        raise RuntimeError("local browser port disagrees with the selected fixture")
    diagnostic_plan = json.loads(Path("docs/contracts/examples/ui-plan.v1.json").read_text())
    diagnostic_plan.update(
        target_id=environment.target_id,
        fixture_id=environment.fixture_id,
        steps=[step.model_dump(mode="json") for step in steps],
    )
    spec = AttackSpec.model_validate(diagnostic_plan)
    observation = Observation(
        observation_id=subject.observation_id,
        attack_id=spec.attack_id,
        environment_id=environment.environment_id,
        source_sha=environment.source_sha,
        fixture_checksum=environment.fixture_checksum,
        status="completed",
        action_log=tuple(records),
        evidence_ids=tuple(dict.fromkeys(e for record in records for e in record.evidence_ids)),
    )
    verdict = await StoredBrowserOracle(
        store, primary_targets={environment.target_id: "checkout-primary-action"}
    ).evaluate("ui.primary_action_reachable", spec, observation, subject)
    expected_verdict = "pass" if variant == "base" else "fail"
    if verdict.outcome != expected_verdict:
        raise RuntimeError("stored browser oracle disagrees with the selected fixture")
    artifacts: list[dict[str, object]] = []
    for record in records:
        expected_subject = subject.model_copy(update={"step_index": record.step_index})
        for artifact_id in record.evidence_ids:
            stored = await store.get(artifact_id)
            if (
                stored is None
                or not (
                    await check_evidence(store, stored.binding.evidence, expected_subject)
                ).trusted
            ):
                raise RuntimeError("browser port evidence failed binding verification")
            artifacts.append(
                {
                    "artifact_id": artifact_id,
                    "media_type": stored.binding.evidence.media_type,
                    "step_index": record.step_index,
                }
            )
            if record.action == "capture":
                (output / "final.png").write_bytes(stored.content)
    report: dict[str, object] = {
        "mode": "local_headless_browser_port_diagnostic",
        "variant": variant,
        "checkout_sha": checkout_sha,
        "server_source_verified": False,
        "subject": subject.model_dump(mode="json"),
        "outcomes": [record.outcome for record in records],
        "oracle_outcome": verdict.outcome,
        "oracle_evidence_ids": verdict.evidence_ids,
        "plan_source": "fixed_local_diagnostic",
        "artifacts": artifacts,
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("variant", choices=("base", "head"))
    parser.add_argument("--origin", required=True)
    parser.add_argument("--chrome", type=Path, required=True)
    parser.add_argument("--fixture-repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            asyncio.run(
                probe(args.variant, args.origin, args.chrome, args.fixture_repo, args.output)
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
