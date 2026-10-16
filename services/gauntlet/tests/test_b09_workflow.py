"""A workflow verdict comes from real browser actions and bound evidence."""

import asyncio
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest
from image_samples import JPEG, PNG

from gauntlet.contracts import AttackSpec, EvidenceSubject
from gauntlet.integrations.browser_evidence import BrowserEvidenceCollector
from gauntlet.integrations.local_artifacts import LocalArtifactStore
from gauntlet.integrations.local_browser import LocalBrowserProvider
from gauntlet.ports.artifacts import StoredArtifact
from gauntlet.ports.sandbox import EnvironmentHandle
from gauntlet.verification.catalog import OracleCatalog
from gauntlet.verification.workflow import DESCRIPTOR, WorkflowCompletionOracle
from gauntlet.workers.ui import UIWorker

CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def _spec() -> AttackSpec:
    return AttackSpec.model_validate(
        {
            "attack_id": "workflow-checkout",
            "hypothesis": "Checkout could fail after browsing the product",
            "why_this_change": "Checkout action changed",
            "expected_observation": "The order receipt is visible after submit",
            "source_refs": [
                {"path": "src/checkout.tsx", "sha": "a" * 40, "start_line": 1, "end_line": 2}
            ],
            "worker_kind": "workflow",
            "target_id": "cartwheel-fixture",
            "fixture_id": "baseline-v1",
            "steps": [
                {"action": "navigate", "path": "/products/demo"},
                {"action": "navigate", "path": "/checkout"},
                {"action": "click", "target": "checkout-primary-action"},
                {"action": "inspect", "target": "order-receipt"},
            ],
            "oracle_ids": [DESCRIPTOR.oracle_id],
            "max_actions": 5,
            "max_runtime_seconds": 20,
        }
    )


def _server(*, covered: bool) -> tuple[ThreadingHTTPServer, Thread]:
    overlay = (
        '<div data-testid="overlay" style="position:absolute;top:35px;left:8px;'
        'width:140px;height:50px;z-index:2"></div>'
        if covered
        else ""
    )
    html = f"""<!doctype html><html><body>
      <button data-testid="checkout-primary-action" id="submit"
        style="position:absolute;top:40px;left:10px;width:120px;height:40px">Submit</button>
      {overlay}
      <div data-testid="order-receipt" id="done"
        style="display:none;position:absolute;top:140px;left:10px;width:130px;height:40px">Complete</div>
      <script>document.getElementById('submit').onclick = () => {{
        document.getElementById('done').style.display = 'block';
      }};</script></body></html>""".encode()
    product = b'<h1 data-testid="product-detail">Demo Wheel</h1>'

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = product if self.path == "/products/demo" else html
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


@pytest.mark.skipif(not CHROME.exists(), reason="local Chrome is needed for browser evidence")
@pytest.mark.parametrize("image_format", ["png", "jpeg"])
@pytest.mark.parametrize("covered,expected", [(False, "pass"), (True, "fail")])
def test_checkout_workflow_from_real_browser(
    tmp_path: Path, covered: bool, expected: str, image_format: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = pytest.importorskip("playwright.async_api")
    async_playwright = api.async_playwright
    original_screenshot = api.Page.screenshot

    async def screenshot(page: object, **kwargs: object) -> bytes:
        kwargs["type"] = image_format
        return await original_screenshot(page, **kwargs)

    monkeypatch.setattr(api.Page, "screenshot", screenshot)

    server, thread = _server(covered=covered)

    async def go() -> None:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(executable_path=str(CHROME), headless=True)
            try:
                store = LocalArtifactStore(tmp_path / "evidence")
                provider = LocalBrowserProvider(browser, BrowserEvidenceCollector(store))
                env = EnvironmentHandle(
                    "workflow-env",
                    "cartwheel-fixture",
                    "a" * 40,
                    "baseline-v1",
                    "b" * 64,
                    f"http://127.0.0.1:{server.server_port}",
                )
                subject = EvidenceSubject(
                    run_id="workflow-run",
                    attempt_id="workflow-attempt",
                    observation_id="workflow-observation",
                    environment_id=env.environment_id,
                    source_sha=env.source_sha,
                    fixture_checksum=env.fixture_checksum,
                    collector="browser_collector",
                )
                spec = _spec()
                observation = await UIWorker(
                    provider, OracleCatalog([], DESCRIPTOR), kind="workflow"
                ).run(spec, env, subject)
                verdict = await WorkflowCompletionOracle(
                    store,
                    targets={"cartwheel-fixture": ("checkout-primary-action", "order-receipt")},
                ).evaluate(DESCRIPTOR.oracle_id, spec, observation, subject)
                assert verdict.outcome == expected, (verdict.observed, observation.model_dump())
                assert verdict.oracle_kind == "hard"
                assert verdict.evidence_ids
                unbound = observation.model_copy(update={"evidence_ids": ()})
                assert (
                    await WorkflowCompletionOracle(
                        store,
                        targets={"cartwheel-fixture": ("checkout-primary-action", "order-receipt")},
                    ).evaluate(DESCRIPTOR.oracle_id, spec, unbound, subject)
                ).outcome == "inconclusive"

                screenshot_id = observation.action_log[2].evidence_ids[1]

                class AlteredScreenshotStore:
                    async def get(self, artifact_id: str) -> StoredArtifact | None:
                        stored = await store.get(artifact_id)
                        if artifact_id != screenshot_id or stored is None:
                            return stored
                        if alteration == "missing":
                            return None
                        if alteration == "corrupt":
                            return StoredArtifact(stored.binding, stored.content + b"corrupt")
                        if alteration == "wrong_media":
                            evidence = stored.binding.evidence.model_copy(
                                update={"media_type": "application/json"}
                            )
                            return StoredArtifact(
                                stored.binding.model_copy(update={"evidence": evidence}),
                                stored.content,
                            )
                        if alteration in {"invalid_png", "mislabeled", "truncated"}:
                            content = b"not a PNG"
                            if alteration == "mislabeled":
                                content = JPEG if image_format == "png" else PNG
                            elif alteration == "truncated":
                                content = stored.content[:-2]
                            evidence = stored.binding.evidence.model_copy(
                                update={"sha256": hashlib.sha256(content).hexdigest()}
                            )
                            return StoredArtifact(
                                stored.binding.model_copy(
                                    update={"evidence": evidence, "byte_size": len(content)}
                                ),
                                content,
                            )
                        wrong_subject = stored.binding.subject.model_copy(
                            update={"attempt_id": "different-attempt"}
                        )
                        return StoredArtifact(
                            stored.binding.model_copy(update={"subject": wrong_subject}),
                            stored.content,
                        )

                for alteration in (
                    "missing",
                    "corrupt",
                    "wrong_subject",
                    "wrong_media",
                    "invalid_png",
                    "mislabeled",
                    "truncated",
                ):
                    tampered = await WorkflowCompletionOracle(
                        AlteredScreenshotStore(),
                        targets={"cartwheel-fixture": ("checkout-primary-action", "order-receipt")},
                    ).evaluate(DESCRIPTOR.oracle_id, spec, observation, subject)
                    assert tampered.outcome == "inconclusive", alteration
                if covered:
                    assert observation.action_log[2].outcome == "blocked"
                    assert len(observation.action_log) == 3
                else:
                    assert observation.status == "completed"
                    assert observation.action_log[3].outcome == "ok"
            finally:
                await browser.close()

    try:
        asyncio.run(go())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
