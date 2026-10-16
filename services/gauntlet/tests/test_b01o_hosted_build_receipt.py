"""A registered hosted build receipt gates each provider browser action."""

import asyncio
import gzip
import json
from pathlib import Path

import httpx
import pytest
from test_b01_provider_smoke import (
    BASE,
    CHECKSUM,
    HEAD,
    RecordingBrowser,
    RecordingSandbox,
    change,
    target,
)

from gauntlet.execution.provider_smoke import capture_provider_pair
from gauntlet.integrations.fixture_identity import verify_hosted_fixture_build_receipt
from gauntlet.integrations.local_artifacts import LocalArtifactStore
from gauntlet.ports.errors import EnvironmentUnavailableError

ORIGIN = "https://signed-base.proxy.daytona.work"
SUFFIX = ".proxy.daytona.work"


def check(response: httpx.Response, *, origin: str = ORIGIN) -> list[httpx.Request]:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            response.status_code,
            headers=response.headers,
            stream=httpx.ByteStream(response.content),
        )

    asyncio.run(
        verify_hosted_fixture_build_receipt(
            origin, BASE, preview_domain_suffix=SUFFIX, transport=httpx.MockTransport(respond)
        )
    )
    return requests


def test_registered_signed_origin_fetches_exact_raw_receipt() -> None:
    requests = check(httpx.Response(200, json={"schema_version": "1.0", "source_sha": BASE}))
    assert len(requests) == 1
    assert str(requests[0].url) == f"{ORIGIN}/api/build-info"
    assert requests[0].method == "GET"
    assert requests[0].headers["accept-encoding"] == "identity"


@pytest.mark.parametrize(
    "origin",
    [
        "http://signed-base.proxy.daytona.work",
        "https://signed-base.proxy.daytona.work:443",
        "https://user@signed-base.proxy.daytona.work",
        "https://signed-base.proxy.daytona.work/",
        "https://signed-base.proxy.daytona.work/path",
        "https://signed-base.proxy.daytona.work?x=1",
        "https://signed-base.proxy.daytona.work#frag",
        "https://signed-base.proxy.daytona.work.evil.invalid",
        "https://proxy.daytona.work",
        "https://signed-base..proxy.daytona.work",
        "https://SIGNED-BASE.proxy.daytona.work",
    ],
)
def test_invalid_hosted_origin_never_reaches_http(origin: str) -> None:
    def unexpected(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("invalid origin reached HTTP")

    with pytest.raises(EnvironmentUnavailableError, match="origin"):
        asyncio.run(
            verify_hosted_fixture_build_receipt(
                origin,
                BASE,
                preview_domain_suffix=SUFFIX,
                transport=httpx.MockTransport(unexpected),
            )
        )


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json={"schema_version": "1.0", "source_sha": HEAD}),
        httpx.Response(302, headers={"location": "https://attacker.invalid"}),
        httpx.Response(200, content=b"x" * 4097, headers={"content-type": "application/json"}),
        httpx.Response(
            200,
            content=gzip.compress(
                b'{"schema_version":"1.0","source_sha":"' + BASE.encode() + b'"}'
            ),
            headers={"content-type": "application/json", "content-encoding": "gzip"},
        ),
        httpx.Response(
            200,
            content=(
                b'{"schema_version":"1.0","source_sha":"'
                + BASE.encode()
                + b'","source_sha":"'
                + BASE.encode()
                + b'"}'
            ),
            headers={"content-type": "application/json"},
        ),
    ],
)
def test_hosted_receipt_reuses_strict_parser(response: httpx.Response) -> None:
    with pytest.raises(EnvironmentUnavailableError, match="receipt"):
        check(response)


def test_transport_error_does_not_expose_signed_origin_or_secret() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("secret proxy credential", request=request)

    with pytest.raises(EnvironmentUnavailableError) as error:
        asyncio.run(
            verify_hosted_fixture_build_receipt(
                ORIGIN,
                BASE,
                preview_domain_suffix=SUFFIX,
                transport=httpx.MockTransport(fail),
            )
        )
    assert "secret" not in str(error.value)
    assert ORIGIN not in str(error.value)


@pytest.mark.parametrize("stale_revision", [BASE, HEAD])
def test_stale_build_blocks_its_browser_open_and_cleans_pair(
    tmp_path: Path, stale_revision: str
) -> None:
    async def scenario() -> None:
        sandbox = RecordingSandbox()
        store = LocalArtifactStore(tmp_path)
        browser = RecordingBrowser(store)
        requested: list[str] = []

        def respond(request: httpx.Request) -> httpx.Response:
            sha = BASE if request.url.host.startswith("signed-base.") else HEAD
            requested.append(sha)
            if sha == stale_revision:
                sha = "f" * 40
            return httpx.Response(
                200,
                stream=httpx.ByteStream(
                    json.dumps({"schema_version": "1.0", "source_sha": sha}).encode()
                ),
                headers={"content-type": "application/json"},
            )

        with pytest.raises(EnvironmentUnavailableError, match="selected SHA"):
            await capture_provider_pair(
                sandbox,
                browser,
                store,
                change(),
                CHECKSUM,
                ready_path="/checkout",
                registered_target=target(),
                receipt_transport=httpx.MockTransport(respond),
            )
        assert requested == ([BASE] if stale_revision == BASE else [BASE, HEAD])
        assert browser.navigated == ([] if stale_revision == BASE else [BASE])
        assert len(browser.opened) == (0 if stale_revision == BASE else 1)
        assert browser.sessions == {}
        assert len(sandbox.created) == 2
        assert all(
            [
                not await sandbox.verify_fixture(env.environment_id, CHECKSUM)
                for env in sandbox.created
            ]
        )

    asyncio.run(scenario())


def test_missing_registration_fails_before_resource_creation(tmp_path: Path) -> None:
    async def scenario() -> None:
        sandbox = RecordingSandbox()
        store = LocalArtifactStore(tmp_path)
        browser = RecordingBrowser(store)
        with pytest.raises(EnvironmentUnavailableError, match="registration"):
            await capture_provider_pair(
                sandbox, browser, store, change(), CHECKSUM, ready_path="/checkout"
            )
        assert sandbox.created == []
        assert browser.opened == []

    asyncio.run(scenario())
