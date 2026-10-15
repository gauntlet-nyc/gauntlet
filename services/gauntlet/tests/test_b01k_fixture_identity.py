"""A local Gate probe accepts only the selected Cartwheel build receipt."""

import asyncio
import importlib.util
from pathlib import Path
from types import ModuleType

import httpx
import pytest

from gauntlet.integrations.fixture_identity import verify_fixture_build_receipt
from gauntlet.ports.errors import EnvironmentUnavailableError

SHA = "a" * 40
ORIGIN = "http://127.0.0.1:3100"
ROOT = Path(__file__).resolve().parents[3]


def receipt(**changes: object) -> dict[str, object]:
    return {"schema_version": "1.0", "source_sha": SHA, **changes}


def check_response(response: httpx.Response, *, origin: str = ORIGIN, sha: str = SHA) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return response

    asyncio.run(verify_fixture_build_receipt(origin, sha, transport=httpx.MockTransport(respond)))
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
        httpx.Response(
            200,
            content=b"{" + b'"source_sha":"' + SHA.encode() + b'"}',
            headers={"content-type": "application/json"},
        ),
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


def test_duplicate_json_fields_are_rejected() -> None:
    body = (
        b'{"schema_version":"1.0","source_sha":"'
        + SHA.encode()
        + b'","source_sha":"'
        + SHA.encode()
        + b'"}'
    )
    with pytest.raises(EnvironmentUnavailableError, match="receipt"):
        check_response(
            httpx.Response(200, content=body, headers={"content-type": "application/json"})
        )


def test_invalid_expected_sha_is_rejected_before_request() -> None:
    def unexpected(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("invalid SHA reached transport")

    with pytest.raises(EnvironmentUnavailableError, match="full expected SHA"):
        asyncio.run(
            verify_fixture_build_receipt(
                ORIGIN, "a" * 39, transport=httpx.MockTransport(unexpected)
            )
        )


def test_transport_failure_is_sanitized() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("private proxy secret", request=request)

    with pytest.raises(EnvironmentUnavailableError, match="receipt") as error:
        asyncio.run(verify_fixture_build_receipt(ORIGIN, SHA, transport=httpx.MockTransport(fail)))
    assert "private proxy secret" not in str(error.value)


def _load_script(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_probe_rejects_receipt_before_plan_freeze_or_browser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builder = _load_script(ROOT / "scripts/build_cartwheel_fixture.py", "cartwheel_builder")
    repo = tmp_path / "cartwheel"
    builder.build(repo)
    probe = _load_script(ROOT / "scripts/probe_p1_local_gate.py", "local_gate_probe")
    calls: list[tuple[str, str]] = []

    async def reject(origin: str, expected_sha: str) -> None:
        calls.append((origin, expected_sha))
        raise EnvironmentUnavailableError("Cartwheel build receipt does not match")

    async def unexpected_freeze(*_args: object) -> None:
        raise AssertionError("plan froze before receipt validation")

    monkeypatch.setattr(probe, "verify_fixture_build_receipt", reject)
    monkeypatch.setattr(probe, "freeze_diagnostic_plan", unexpected_freeze)
    with pytest.raises(EnvironmentUnavailableError, match="receipt"):
        asyncio.run(probe.probe("head", ORIGIN, tmp_path / "chrome", repo, tmp_path / "out"))
    assert calls == [(ORIGIN, builder.git(repo, "rev-parse", "HEAD"))]
    assert not (tmp_path / "out").exists()
