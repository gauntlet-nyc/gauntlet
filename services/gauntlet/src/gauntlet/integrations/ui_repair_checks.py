"""Trusted legitimate Cartwheel UI actions for approved local repair verification.

Browser routing is a local guard, not a claim of operating-system isolation.
No target text supplies selectors, executable scripts, origins or expectations.
"""

from urllib.parse import urlsplit

from gauntlet.application.gate.repair import CheckResult
from gauntlet.integrations.fixture_identity import (
    canonical_loopback_origin,
    verify_fixture_build_receipt,
)
from gauntlet.ports.errors import EnvironmentUnavailableError
from gauntlet.ports.sandbox import EnvironmentHandle

_VIEWPORTS = (("mobile", 375, 812), ("desktop", 1280, 900))


async def check_ui_features(
    environment: EnvironmentHandle, *, chromium_path: str | None = None
) -> tuple[CheckResult, ...]:
    """Require Help open/close and an actual checkout action at both fixed viewports."""
    try:
        if environment.target_id != "cartwheel-fixture":
            raise EnvironmentUnavailableError("unsupported repair target")
        origin = canonical_loopback_origin(environment.preview_origin)
        await verify_fixture_build_receipt(origin, environment.source_sha)
        from playwright.async_api import Error, Route, WebSocketRoute, async_playwright, expect
    except (EnvironmentUnavailableError, ImportError) as exc:
        return (CheckResult("ui-features-environment", False, f"environment_error: {exc}"),)

    results: list[CheckResult] = []
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(executable_path=chromium_path)
            try:
                for name, width, height in _VIEWPORTS:
                    context = await browser.new_context(
                        viewport={"width": width, "height": height},
                        service_workers="block",
                        accept_downloads=False,
                    )
                    blocked = False

                    async def guard(route: Route) -> None:
                        nonlocal blocked
                        url = urlsplit(route.request.url)
                        if f"{url.scheme}://{url.netloc}" != origin:
                            blocked = True
                            await route.abort()
                            return
                        try:
                            response = await route.fetch(max_redirects=0, timeout=5000)
                            if 300 <= response.status < 400:
                                blocked = True
                                await route.abort()
                            else:
                                await route.fulfill(response=response)
                        except Error:
                            blocked = True
                            try:
                                await route.abort()
                            except Error:
                                pass  # Context teardown is the final boundary.

                    async def block_socket(socket: WebSocketRoute) -> None:
                        nonlocal blocked
                        blocked = True
                        await socket.close()

                    try:
                        await context.route("**/*", guard)
                        await context.route_web_socket("**/*", block_socket)
                        page = await context.new_page()
                        page.set_default_timeout(3000)
                        response = await page.goto(
                            f"{origin}/checkout", wait_until="networkidle", timeout=10000
                        )
                        if (
                            response is None
                            or response.status != 200
                            or page.url != f"{origin}/checkout"
                        ):
                            raise EnvironmentUnavailableError("checkout navigation failed")
                        help_button = page.get_by_test_id("help-button")
                        dialog = page.get_by_role("dialog", name="Help", exact=True)
                        checkout = page.get_by_test_id("checkout-primary-action")
                        receipt = page.get_by_test_id("order-receipt")
                        await expect(help_button).to_be_visible()
                        await expect(checkout).to_be_visible()
                        await expect(dialog).to_be_hidden()
                        await expect(receipt).to_be_hidden()
                        await help_button.click()
                        await expect(dialog).to_be_visible(timeout=3000)
                        await help_button.click()
                        await expect(dialog).to_be_hidden(timeout=3000)
                        await checkout.click()
                        await expect(receipt).to_be_visible(timeout=3000)
                        await verify_fixture_build_receipt(origin, environment.source_sha)
                        if blocked:
                            raise EnvironmentUnavailableError(
                                "browser request left allowed scope or failed"
                            )
                        results.append(
                            CheckResult(
                                f"ui-features-{name}",
                                True,
                                "Help opens/closes and checkout produces a visible receipt",
                            )
                        )
                    except (Error, AssertionError, EnvironmentUnavailableError) as exc:
                        kind = (
                            "environment_error"
                            if isinstance(exc, EnvironmentUnavailableError) or blocked
                            else "failed"
                        )
                        results.append(
                            CheckResult(
                                f"ui-features-{name}",
                                False,
                                f"{kind}: UI actions did not complete ({type(exc).__name__})",
                            )
                        )
                    finally:
                        await context.close()
            finally:
                await browser.close()
    except Error:
        results.append(
            CheckResult(
                "ui-features-environment", False, "environment_error: browser could not run"
            )
        )
    return tuple(results)
