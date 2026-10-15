"""A local Gate probe accepts only the selected Cartwheel build receipt."""

import asyncio

import httpx
import pytest

from gauntlet.integrations.fixture_identity import verify_fixture_build_receipt
from gauntlet.ports.errors import EnvironmentUnavailableError

SHA = "a" * 40
ORIGIN = "http://127.0.0.1:3100"


def receipt(**changes: object) -> dict[str, object]:
    return {"schema_version": "1.0", "source_sha": SHA, **changes}


def check_response(response: httpx.Response, *, origin: str = ORIGIN, sha: str = SHA) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return response

    asyncio.run(
        verify_fixture_build_receipt(origin, sha, transport=httpx.MockTransport(respond))
    )
    assert len(requests) == 1
    assert str(requests[0].url) == f"{ORIGIN}/api/build-info"
    assert requests[0].method == "GET"


def test_valid_receipt_matches_selected_build() -> None:
    check_response(httpx.Response(200, json=receipt()))


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json=receipt(source_sha="b" * 40)),
        httpx.Response(200, json=receipt(unexpected=True)),
        httpx.Response(200, json=receipt(schema_version="2.0")),
        httpx.Response(200, json=receipt(source_sha="a" * 39)),
        httpx.Response(200, content=b"not-json", headers={"content-type": "application/json"}),
        httpx.Response(200, content=b'{' + b'"source_sha":"' + SHA.encode() + b'"}'),
        httpx.Response(200, json=receipt(), headers={"content-type": "text/plain"}),
    ],
)
def test_invalid_receipts_fail_closed(response: httpx.Response) -> None:
    with pytest.raises(EnvironmentUnavailableError, match="receipt") as error:
        check_response(response)
    assert SHA not in str(error.value)


def test_redirect_is_not_followed() -> None:
    with pytest.raises(EnvironmentUnavailableError, match="receipt"):
        check_response(
            httpx.Response(302, headers={"location": "https://attacker.invalid/build-info"})
        )


@pytest.mark.parametrize(
    "origin",
    [
        "https://127.0.0.1:3100",
        "http://localhost:3100",
        "http://127.0.0.2:3100",
        "http://user@127.0.0.1:3100",
        "http://127.0.0.1:3100/path",
        "http://127.0.0.1:3100?x=1",
        "http://127.0.0.1:3100#fragment",
        "http://127.0.0.1:3100/",
    ],
)
def test_noncanonical_or_external_origin_is_rejected_before_request(origin: str) -> None:
    def unexpected(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("invalid origin reached transport")

    with pytest.raises(EnvironmentUnavailableError, match="loopback"):
        asyncio.run(
            verify_fixture_build_receipt(origin, SHA, transport=httpx.MockTransport(unexpected))
        )


def test_oversized_body_is_rejected() -> None:
    with pytest.raises(EnvironmentUnavailableError, match="receipt"):
        check_response(
            httpx.Response(200, content=b"x" * 4097, headers={"content-type": "application/json"})
        )


def test_transport_failure_is_sanitized() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("private proxy secret", request=request)

    with pytest.raises(EnvironmentUnavailableError, match="receipt") as error:
        asyncio.run(
            verify_fixture_build_receipt(ORIGIN, SHA, transport=httpx.MockTransport(fail))
        )
    assert "private proxy secret" not in str(error.value)
