"""The known Cartwheel workflow has a registered executor and trusted oracle."""

import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from gauntlet import composition
from gauntlet.composition import GateTarget, build_gate
from gauntlet.contracts import ClickStep, EvidenceSubject, InspectStep, NavigateStep
from gauntlet.integrations.browser_evidence import BrowserEvidenceCollector
from gauntlet.integrations.local_artifacts import LocalArtifactStore
from gauntlet.integrations.local_browser import LocalBrowserProvider
from gauntlet.ports.sandbox import EnvironmentHandle
from gauntlet.settings import Settings
from gauntlet.verification.workflow import DESCRIPTOR
from gauntlet.workers.ui import UIWorker


def test_cartwheel_workflow_is_wired_to_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def browser_stub(*args: object) -> tuple[object, str]:
        return object(), "local_test_browser"

    monkeypatch.setattr(composition, "_build_browser", browser_stub)

    async def scenario() -> None:
        runtime = await build_gate(
            Settings.from_env(
                {
                    "CARTWHEEL_BASE_ORIGIN": "http://127.0.0.1:3101",
                    "CARTWHEEL_HEAD_ORIGIN": "http://127.0.0.1:3102",
                }
            ),
            GateTarget.cartwheel(tmp_path),
            model="scripted",
            sandbox="local",
            browser="local",
            artifact_root=tmp_path / "artifacts",
        )
        try:
            assert "workflow" in runtime.routes
            executor = runtime.routes["workflow"].executor
            assert isinstance(executor._worker, UIWorker)
            assert executor._worker.kind == "workflow"
            catalog = runtime.use_case._deps.plan_change._deps.planner._oracles
            assert catalog.is_registered(DESCRIPTOR.oracle_id)
            assert "order-receipt" in catalog.descriptor(DESCRIPTOR.oracle_id).description
        finally:
            await runtime.aclose()

    asyncio.run(scenario())


def test_simulated_browser_does_not_advertise_workflow(tmp_path: Path) -> None:
    async def scenario() -> None:
        runtime = await build_gate(
            Settings.from_env({}),
            GateTarget.cartwheel(tmp_path),
            model="scripted",
            sandbox="fake",
            browser="fake",
            artifact_root=tmp_path / "artifacts",
        )
        try:
            assert "workflow" not in runtime.routes
            catalog = runtime.use_case._deps.plan_change._deps.planner._oracles
            assert not catalog.is_registered(DESCRIPTOR.oracle_id)
        finally:
            await runtime.aclose()

    asyncio.run(scenario())


@pytest.mark.skipif(
    not Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome").exists(),
    reason="local Chrome is needed for browser evidence",
)
def test_inspect_waits_for_async_order_receipt(tmp_path: Path) -> None:
    async_playwright = pytest.importorskip("playwright.async_api").async_playwright

    html = b"""<button data-testid="checkout-primary-action"
      style="position:absolute;left:20px;top:20px;width:130px;height:40px"
      onclick="setTimeout(() => document.getElementById('receipt').style.display='block', 300)">
      Place order</button>
      <p id="receipt" data-testid="order-receipt" style="display:none;
      position:absolute;left:20px;top:100px;width:130px;height:40px">Order placed</p>"""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)

        def log_message(self, _format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    async def scenario() -> None:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                headless=True,
            )
            try:
                origin = f"http://127.0.0.1:{server.server_port}"
                store = LocalArtifactStore(tmp_path / "evidence")
                provider = LocalBrowserProvider(browser, BrowserEvidenceCollector(store))
                env = EnvironmentHandle(
                    "env", "cartwheel-fixture", "a" * 40, "baseline-v1", "b" * 64, origin
                )
                subject = EvidenceSubject(
                    run_id="run",
                    attempt_id="attempt",
                    observation_id="observation",
                    environment_id="env",
                    source_sha="a" * 40,
                    fixture_checksum="b" * 64,
                    collector="browser_collector",
                )
                session = await provider.open_session(env, subject)
                try:
                    await provider.perform(session, 0, NavigateStep(path="/checkout"))
                    click = await provider.perform(
                        session, 1, ClickStep(target="checkout-primary-action")
                    )
                    assert click.outcome == "ok"
                    inspected = await provider.perform(
                        session, 2, InspectStep(target="order-receipt")
                    )
                    assert inspected.outcome == "ok"
                    assert inspected.evidence_ids
                finally:
                    await provider.close_session(session)
            finally:
                await browser.close()

    try:
        asyncio.run(scenario())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
