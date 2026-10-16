"""Trusted repair feature checks exercise real local browser actions."""

import asyncio
import json
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from gauntlet.ports.sandbox import EnvironmentHandle

CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
SHA = "a" * 40


@contextmanager
def fixture(mode: str = "good") -> Iterator[tuple[EnvironmentHandle, list[str]]]:
    requests: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            requests.append(self.path)
            if mode == "redirect" and self.path == "/checkout":
                self.send_response(302)
                self.send_header("Location", "/redirect-followed")
                self.end_headers()
                return
            if self.path == "/api/build-info":
                body = json.dumps(
                    {
                        "schema_version": "1.0",
                        "source_sha": ("b" * 40 if mode == "wrong-sha" else SHA),
                    }
                ).encode()
                media = "application/json"
            else:
                help_action = (
                    ""
                    if mode == "broken-help"
                    else ("const d=document.querySelector('[role=dialog]');d.hidden=!d.hidden")
                )
                checkout_action = (
                    ""
                    if mode == "broken-checkout"
                    else "document.querySelector('[data-testid=order-receipt]').hidden=false"
                )
                extra = '<img src="http://127.0.0.1:1/forbidden">' if mode == "egress" else ""
                body = f'''<html><body>{extra}
                <div role="dialog" aria-label="Help" hidden>Help text</div>
                <button data-testid="help-button" onclick="{help_action}">Help</button>
                <button data-testid="checkout-primary-action"
                  onclick="{checkout_action}">Place order</button>
                <div data-testid="order-receipt" hidden>Order placed</div></body></html>'''.encode()
                media = "text/html"
            self.send_response(200)
            self.send_header("Content-Type", media)
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    env = EnvironmentHandle(
        "test",
        "cartwheel-fixture",
        SHA,
        "baseline-v1",
        "c" * 64,
        f"http://127.0.0.1:{server.server_port}",
    )
    try:
        yield env, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.skipif(not CHROME.exists(), reason="local Chrome required")
@pytest.mark.parametrize(
    "mode,passed",
    [
        ("good", True),
        ("broken-help", False),
        ("broken-checkout", False),
        ("egress", False),
        ("redirect", False),
    ],
)
def test_actual_controls_must_work(mode: str, passed: bool) -> None:
    pytest.importorskip("playwright.async_api")
    from gauntlet.integrations.ui_repair_checks import check_ui_features

    with fixture(mode) as (env, requests):
        checks = asyncio.run(check_ui_features(env, chromium_path=str(CHROME)))
    assert len(checks) == 2
    assert all(check.passed for check in checks) is passed
    assert {check.name for check in checks} == {"ui-features-mobile", "ui-features-desktop"}
    assert "/api/build-info" in requests
    assert "/redirect-followed" not in requests


def test_wrong_receipt_prevents_browser_actions() -> None:
    from gauntlet.integrations.ui_repair_checks import check_ui_features

    with fixture("wrong-sha") as (env, requests):
        checks = asyncio.run(check_ui_features(env, chromium_path="/does-not-exist"))
    assert not any(check.passed for check in checks)
    assert requests == ["/api/build-info"]
    assert "environment_error" in checks[0].detail


@pytest.mark.parametrize(
    "origin,target",
    [("https://example.invalid", "cartwheel-fixture"), ("http://127.0.0.1:1234", "other")],
)
def test_rejects_unregistered_scope(origin: str, target: str) -> None:
    from gauntlet.integrations.ui_repair_checks import check_ui_features

    env = EnvironmentHandle("test", target, SHA, "baseline-v1", "c" * 64, origin)
    checks = asyncio.run(check_ui_features(env))
    assert not any(check.passed for check in checks)
    assert "environment_error" in checks[0].detail
