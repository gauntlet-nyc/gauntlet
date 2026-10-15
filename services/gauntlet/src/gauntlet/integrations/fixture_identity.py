"""Read the trusted synthetic Cartwheel build receipt before local UI execution."""

import asyncio
import json
import re
from typing import Literal
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from gauntlet.ports.errors import EnvironmentUnavailableError

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_MAX_RECEIPT_BYTES = 4096


class _BuildReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["1.0"]
    source_sha: str = Field(min_length=40, max_length=40, pattern=r"^[0-9a-f]{40}$")


def _loopback_origin(origin: str) -> str:
    try:
        parsed = urlsplit(origin)
        host = parsed.hostname
        port = parsed.port
    except (TypeError, ValueError):
        host = None
        port = None
    if host not in {"127.0.0.1", "::1"} or port is None or not 1 <= port <= 65535:
        raise EnvironmentUnavailableError(
            "Cartwheel receipt requires an exact loopback HTTP origin"
        )
    canonical = f"http://[{host}]:{port}" if host == "::1" else f"http://{host}:{port}"
    if origin != canonical:
        raise EnvironmentUnavailableError(
            "Cartwheel receipt requires an exact loopback HTTP origin"
        )
    return canonical


def _unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    values: dict[str, object] = {}
    for key, value in pairs:
        if key in values:
            raise ValueError("duplicate receipt field")
        values[key] = value
    return values


async def verify_fixture_build_receipt(
    origin: str,
    expected_sha: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    """Require a bounded compiled-build SHA match from an exact local origin.

    The transport hook supports offline tests; client security settings are fixed.
    This trusted fixture receipt does not attest a hostile target or image.
    """
    base = _loopback_origin(origin)
    if not isinstance(expected_sha, str) or _SHA.fullmatch(expected_sha) is None:
        raise EnvironmentUnavailableError("Cartwheel receipt requires a full expected SHA")
    try:
        async with asyncio.timeout(3):
            async with httpx.AsyncClient(
                transport=transport,
                trust_env=False,
                follow_redirects=False,
                timeout=httpx.Timeout(2, connect=1),
            ) as client:
                async with client.stream(
                    "GET",
                    f"{base}/api/build-info",
                    headers={
                        "accept": "application/json",
                        "accept-encoding": "identity",
                        "cache-control": "no-store",
                    },
                ) as response:
                    if response.status_code != 200:
                        raise EnvironmentUnavailableError("Cartwheel build receipt is unavailable")
                    encoding = response.headers.get("content-encoding")
                    if encoding is not None and encoding.strip().lower() != "identity":
                        raise EnvironmentUnavailableError("Cartwheel build receipt is encoded")
                    if response.headers.get("content-type", "").split(";", 1)[0].lower() != (
                        "application/json"
                    ):
                        raise EnvironmentUnavailableError("Cartwheel build receipt is malformed")
                    body = bytearray()
                    async for chunk in response.aiter_raw(chunk_size=1024):
                        if len(body) + len(chunk) > _MAX_RECEIPT_BYTES:
                            raise EnvironmentUnavailableError(
                                "Cartwheel build receipt is oversized"
                            )
                        body.extend(chunk)
        receipt = _BuildReceipt.model_validate(json.loads(body, object_pairs_hook=_unique_keys))
    except (httpx.HTTPError, TimeoutError, ValidationError, ValueError, UnicodeDecodeError):
        raise EnvironmentUnavailableError(
            "Cartwheel build receipt is invalid or unavailable"
        ) from None
    if receipt.source_sha != expected_sha:
        raise EnvironmentUnavailableError("Cartwheel build receipt does not match the selected SHA")
