"""Local-only Cartwheel browser evidence probe; no Daytona or Anchor calls.

Requires the optional live-providers dependency group for Playwright and an
already running synthetic Cartwheel server from the indicated fixture checkout.
The checkout SHA is verified locally; the running server revision is asserted
by the operator, so this remains diagnostic evidence.
"""

import argparse
import asyncio
import json
import subprocess
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from playwright.async_api import Request, Route, async_playwright

from gauntlet.application.evidence import check_evidence
from gauntlet.contracts import EvidenceSubject
from gauntlet.integrations.browser_evidence import BrowserEvidenceCollector
from gauntlet.integrations.local_artifacts import LocalArtifactStore


async def probe(
    variant: str, origin: str, chrome: Path, fixture_repo: Path, output: Path
) -> dict[str, object]:
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.port is None
    ):
        raise ValueError("origin must be an exact loopback HTTP origin with a port")
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
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(executable_path=str(chrome), headless=True)
        try:
            context = await browser.new_context(
                viewport={"width": 375, "height": 812},
                service_workers="block",
                accept_downloads=False,
            )
            try:

                async def route_request(route: Route) -> None:
                    request_url = urlsplit(route.request.url)
                    if (request_url.scheme, request_url.netloc) != (parsed.scheme, parsed.netloc):
                        await route.abort()
                    else:
                        await route.continue_()

                await context.route("**/*", route_request)
                page = await context.new_page()
                await page.goto(f"{origin}/checkout", wait_until="domcontentloaded")
                await page.get_by_test_id("checkout-primary-action").wait_for()
                if variant == "head":
                    await page.get_by_test_id("help-button").wait_for()
                order_posts: list[str] = []

                def track_order_post(request: Request) -> None:
                    if request.method == "POST" and urlsplit(request.url).path == "/api/orders":
                        order_posts.append(request.url)

                page.on("request", track_order_post)
                collector = BrowserEvidenceCollector(store)
                inspected = await collector.inspect(page, "checkout-primary-action", subject, 2)
                clicked = await collector.click(page, "checkout-primary-action", subject, 3)
                if variant == "base":
                    await page.get_by_test_id("order-receipt").wait_for(timeout=10_000)
                else:
                    await page.wait_for_timeout(400)
                receipt_count = await page.get_by_test_id("order-receipt").count()
                expected = "ok" if variant == "base" else "blocked"
                if inspected.outcome != "ok" or clicked.outcome != expected:
                    raise RuntimeError("headless click outcome disagrees with the selected fixture")
                if (variant == "base" and receipt_count != 1) or (
                    variant == "head" and receipt_count != 0
                ):
                    raise RuntimeError("synthetic order receipt disagrees with the click outcome")
                if len(order_posts) != (1 if variant == "base" else 0):
                    raise RuntimeError("synthetic order POST disagrees with the click outcome")
                server_receipt_verified = False
                if variant == "base":
                    receipt_id = await page.get_by_test_id("order-receipt").get_attribute(
                        "data-order-id"
                    )
                    fetched = await page.evaluate(
                        """async id => {
                          const r = await fetch(`/api/orders/${encodeURIComponent(id)}`);
                          return r.ok ? await r.json() : null;
                        }""",
                        receipt_id,
                    )
                    server_receipt_verified = (
                        isinstance(fetched, dict) and fetched.get("order_id") == receipt_id
                    )
                    if not server_receipt_verified:
                        raise RuntimeError("synthetic order receipt was not retrievable")
                captured = await collector.capture(page, subject, 4)
                artifacts: list[dict[str, object]] = []
                for step_index, record in ((2, inspected), (3, clicked), (4, captured)):
                    expected_subject = EvidenceSubject.model_validate(
                        {**subject.model_dump(), "step_index": step_index}
                    )
                    for artifact_id in record.evidence_ids:
                        stored = await store.get(artifact_id)
                        if (
                            stored is None
                            or not (
                                await check_evidence(
                                    store, stored.binding.evidence, expected_subject
                                )
                            ).trusted
                        ):
                            raise RuntimeError("stored browser evidence failed verification")
                        artifacts.append(
                            {
                                "artifact_id": artifact_id,
                                "media_type": stored.binding.evidence.media_type,
                                "sha256": stored.binding.evidence.sha256,
                                "step_index": stored.binding.subject.step_index,
                            }
                        )
                        if stored.binding.evidence.media_type == "image/png":
                            name = "click.png" if step_index == 3 else "final.png"
                            (output / name).write_bytes(stored.content)
                report: dict[str, object] = {
                    "mode": "local_headless_diagnostic",
                    "variant": variant,
                    "checkout_sha": checkout_sha,
                    "server_source_verified": False,
                    "subject": subject.model_dump(mode="json"),
                    "inspect_outcome": inspected.outcome,
                    "click_outcome": clicked.outcome,
                    "capture_outcome": captured.outcome,
                    "receipt_count": receipt_count,
                    "order_post_count": len(order_posts),
                    "server_receipt_verified": server_receipt_verified,
                    "artifacts": artifacts,
                }
                (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
                return report
            finally:
                await context.close()
        finally:
            await browser.close()


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
