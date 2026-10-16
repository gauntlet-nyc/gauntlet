"""Minimal SurrealDB core client over the HTTP `/rpc` endpoint; plain httpx, no SDK.

Every query is a fixed SurrealQL string from this package with values bound as typed JSON
variables. Nothing here accepts query text from a model, a page or a request.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final
from urllib.parse import urlsplit, urlunsplit

import httpx

from gauntlet.ports.errors import EnvironmentUnavailableError, PortError

_MAX_RESPONSE_BYTES: Final = 8_000_000
_GENERIC_TX_ERROR: Final = "not executed due to a failed transaction"

JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


class SurrealQueryError(PortError):
    """A statement returned status ERR. `detail` is SurrealDB's message (no credentials)."""

    def __init__(self, statement_index: int, detail: str) -> None:
        self.statement_index = statement_index
        self.detail = detail
        super().__init__(f"SurrealDB statement {statement_index} failed: {detail[:300]}")


@dataclass(frozen=True)
class StatementResult:
    ok: bool
    result: JsonValue


def http_base_url(url: str) -> str:
    """Accept ws(s):// or http(s):// and return the HTTP origin used for `/rpc`."""
    parsed = urlsplit(url)
    scheme = {"ws": "http", "wss": "https"}.get(parsed.scheme, parsed.scheme)
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("SurrealDB URL must be http(s) or ws(s)")
    path = parsed.path.rstrip("/")
    if path.endswith("/rpc"):
        path = path[: -len("/rpc")]
    return urlunsplit((scheme, parsed.netloc, path, "", ""))


class SurrealHttpClient:
    """One connection pool; Basic auth root/namespace user; namespace/database via headers."""

    def __init__(
        self,
        *,
        url: str,
        namespace: str,
        database: str,
        user: str | None = None,
        password: str | None = None,
        token: str | None = None,
        timeout_seconds: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Authenticate with Basic `user`/`password`, or with a bearer `token` (not both)."""
        if not namespace or not database:
            raise ValueError("SurrealDB namespace and database are required")
        if bool(token) == bool(user and password):
            raise ValueError("SurrealDB needs either user and password, or a token")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "surreal-ns": namespace,
            "surreal-db": database,
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.AsyncClient(
            base_url=http_base_url(url),
            auth=httpx.BasicAuth(user, password) if user and password else None,
            headers=headers,
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )
        self._next_id = 0

    async def query(
        self, surql: str, variables: Mapping[str, JsonValue] | None = None
    ) -> list[StatementResult]:
        """Run fixed SurrealQL with bound variables. Raise on the first ERR statement."""
        results = await self.query_raw(surql, variables)
        failures = [(index, str(item.result)) for index, item in enumerate(results) if not item.ok]
        if failures:
            # In a failed transaction every statement reports a generic error; surface the cause.
            specific = [item for item in failures if _GENERIC_TX_ERROR not in item[1]]
            raise SurrealQueryError(*(specific or failures)[0])
        return results

    async def query_raw(
        self, surql: str, variables: Mapping[str, JsonValue] | None = None
    ) -> list[StatementResult]:
        self._next_id += 1
        body = {"id": self._next_id, "method": "query", "params": [surql, dict(variables or {})]}
        try:
            response = await self._client.post("/rpc", json=body)
        except httpx.HTTPError as exc:
            raise EnvironmentUnavailableError(
                f"SurrealDB request failed ({type(exc).__name__})"
            ) from None
        if response.status_code in (401, 403):
            raise EnvironmentUnavailableError("SurrealDB rejected the credentials")
        if response.status_code != 200 or len(response.content) > _MAX_RESPONSE_BYTES:
            raise EnvironmentUnavailableError(f"SurrealDB returned HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError:
            raise EnvironmentUnavailableError("SurrealDB returned non-JSON") from None
        if not isinstance(payload, dict):
            raise EnvironmentUnavailableError("SurrealDB returned an unexpected payload")
        if "error" in payload:
            error = payload["error"]
            message = error.get("message") if isinstance(error, dict) else error
            raise SurrealQueryError(0, str(message))
        raw = payload.get("result")
        if not isinstance(raw, list):
            raise EnvironmentUnavailableError("SurrealDB returned an unexpected payload")
        statements: list[StatementResult] = []
        for item in raw:
            if not isinstance(item, dict) or item.get("status") not in ("OK", "ERR"):
                raise EnvironmentUnavailableError("SurrealDB returned an unexpected statement")
            statements.append(StatementResult(ok=item["status"] == "OK", result=item.get("result")))
        return statements

    async def health(self) -> bool:
        try:
            response = await self._client.get("/health")
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    async def close(self) -> None:
        await self._client.aclose()


def rows(result: StatementResult) -> list[dict[str, JsonValue]]:
    if not isinstance(result.result, list):
        raise EnvironmentUnavailableError("SurrealDB statement did not return rows")
    out: list[dict[str, JsonValue]] = []
    for row in result.result:
        if not isinstance(row, dict):
            raise EnvironmentUnavailableError("SurrealDB row is not an object")
        out.append(row)
    return out
