"""Exercise the local browser port's route guard in real headless Chrome."""

import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from uuid import uuid4

from playwright.async_api import async_playwright

from gauntlet.contracts import CaptureStep, ClickStep, EvidenceSubject, NavigateStep
from gauntlet.integrations.browser_evidence import BrowserEvidenceCollector
from gauntlet.integrations.local_artifacts import LocalArtifactStore
from gauntlet.integrations.local_browser import LocalBrowserProvider
from gauntlet.ports.sandbox import EnvironmentHandle


class Trap(BaseHTTPRequestHandler):
    hits = 0
    paths: list[str] = []

    def do_GET(self) -> None:
        Trap.hits += 1
        Trap.paths.append(self.path)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"unexpected egress")

    def log_message(self, *_args: object) -> None:
        pass


def app_handler(trap_origin: str) -> type[BaseHTTPRequestHandler]:
    class App(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", f"{trap_origin}/redirected")
                self.end_headers()
                return
            if self.path == "/subresource":
                html = f'<img src="{trap_origin}/image" />'
            else:
                html = (
                    f'<button data-testid="popup" onclick="window.open(\'{trap_origin}/popup\')">'
                    "Open</button>"
                )
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(html.encode())

        def log_message(self, *_args: object) -> None:
            pass

    return App


async def probe(chrome: Path) -> None:
    Trap.hits = 0
    Trap.paths = []
    trap = ThreadingHTTPServer(("127.0.0.1", 0), Trap)
    trap_origin = f"http://127.0.0.1:{trap.server_port}"
    app = ThreadingHTTPServer(("127.0.0.1", 0), app_handler(trap_origin))
    for server in (trap, app):
        Thread(target=server.serve_forever, daemon=True).start()
    try:
        with TemporaryDirectory(prefix="gauntlet-browser-scope-") as scratch:
            subject = EvidenceSubject(
                run_id=f"scope-run-{uuid4().hex}",
                attempt_id=f"scope-attempt-{uuid4().hex}",
                observation_id=f"scope-observation-{uuid4().hex}",
                environment_id=f"scope-environment-{uuid4().hex}",
                source_sha="a" * 40,
                fixture_checksum="b" * 64,
                collector="browser_collector",
            )
            environment = EnvironmentHandle(
                environment_id=subject.environment_id,
                target_id="scope-synthetic",
                source_sha=subject.source_sha,
                fixture_id="scope-v1",
                fixture_checksum=subject.fixture_checksum,
                preview_origin=f"http://127.0.0.1:{app.server_port}",
            )
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(
                    executable_path=str(chrome), headless=True
                )
                try:
                    adapter = LocalBrowserProvider(
                        browser, BrowserEvidenceCollector(LocalArtifactStore(Path(scratch)))
                    )
                    redirect = await adapter.open_session(environment, subject)
                    try:
                        record = await adapter.perform(redirect, 0, NavigateStep(path="/redirect"))
                        assert record.outcome == "blocked", record
                    finally:
                        await adapter.close_session(redirect)

                    subresource = await adapter.open_session(environment, subject)
                    try:
                        record = await adapter.perform(
                            subresource, 0, NavigateStep(path="/subresource")
                        )
                        await asyncio.sleep(0.2)
                        if record.outcome != "blocked":
                            record = await adapter.perform(subresource, 1, CaptureStep())
                        assert record.outcome == "blocked", record
                    finally:
                        await adapter.close_session(subresource)

                    popup = await adapter.open_session(environment, subject)
                    try:
                        record = await adapter.perform(popup, 0, NavigateStep(path="/popup"))
                        assert record.outcome == "ok", record
                        record = await adapter.perform(popup, 1, ClickStep(target="popup"))
                        assert record.outcome == "blocked", record
                    finally:
                        await adapter.close_session(popup)
                finally:
                    await browser.close()
        assert Trap.hits == 0, f"off-origin server received {Trap.paths}"
        print("redirect=blocked subresource=blocked popup=blocked off_origin_requests=0")
    finally:
        for server in (app, trap):
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome", type=Path, required=True)
    asyncio.run(probe(parser.parse_args().chrome))
