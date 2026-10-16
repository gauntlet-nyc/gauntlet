"""GitHub App adapter: App JWT (RS256) -> installation token -> check runs. Checks-only.

RS256 signing uses `cryptography` (RSASSA-PKCS1-v1_5 over SHA-256), an optional
`live-providers` dependency imported only when a key is loaded. The key file is read
from `GITHUB_PRIVATE_KEY_PATH`, never from the repo or a prompt, and the key never
prints. The publisher only creates/updates check runs. It never pushes, comments,
approves or merges, and the installation token is requested with `checks: write` only.
"""

import base64
import json
import re
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Final
from urllib.parse import quote

import httpx

from gauntlet.ports.code_host import CheckRunReport
from gauntlet.ports.errors import EnvironmentUnavailableError
from gauntlet.settings import IntegrationSettings, require

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric import rsa

_REPO: Final = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_SHA: Final = re.compile(r"^[0-9a-f]{40}$")
_EXTERNAL_ID: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_SUMMARY: Final = 65_000


class RsaPrivateKey:
    """An RSA signing key whose material never appears in repr/str."""

    __slots__ = ("_key",)

    def __init__(self, key: "rsa.RSAPrivateKey") -> None:
        self._key = key

    def __repr__(self) -> str:
        return f"RsaPrivateKey(bits={self._key.key_size})"

    __str__ = __repr__

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, RsaPrivateKey)
            and other._key.private_numbers() == self._key.private_numbers()
        )

    def __hash__(self) -> int:
        return hash(self._key.public_key().public_numbers().n)

    @property
    def key_size(self) -> int:
        return self._key.key_size

    def sign_sha256(self, message: bytes) -> bytes:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding

        return self._key.sign(message, padding.PKCS1v15(), hashes.SHA256())


def parse_rsa_private_key(pem: str, *, min_bits: int = 2048) -> RsaPrivateKey:
    """Accept an unencrypted RSA PEM: PKCS#1 (GitHub's download) or PKCS#8."""
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
    except ImportError:
        raise EnvironmentUnavailableError(
            "missing cryptography (install the live-providers dependency group)"
        ) from None
    try:
        key = serialization.load_pem_private_key(pem.encode("ascii"), password=None)
    except (ValueError, TypeError, UnicodeEncodeError):
        raise ValueError("GitHub App private key is not an unencrypted RSA PEM") from None
    if not isinstance(key, rsa.RSAPrivateKey):
        raise ValueError("GitHub App private key is not RSA")
    if key.key_size < min_bits:
        raise ValueError("RSA key is too small")
    return RsaPrivateKey(key)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def app_jwt(app_id: str, key: RsaPrivateKey, *, now: int | None = None) -> str:
    """GitHub App JWT: iat backdated 60s for clock skew, 9-minute lifetime (max is 10)."""
    issued = int(time.time() if now is None else now) - 60
    header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    claims = {"iat": issued, "exp": issued + 600 - 60, "iss": app_id}
    payload = _b64url(json.dumps(claims, separators=(",", ":")).encode())
    signing_input = f"{header}.{payload}".encode("ascii")
    return f"{header}.{payload}.{_b64url(key.sign_sha256(signing_input))}"


class GitHubAppCheckRunPublisher:
    """`CheckRunPublisher` port over GitHub's REST API with an installation token."""

    def __init__(
        self,
        *,
        app_id: str,
        installation_id: str,
        private_key: RsaPrivateKey,
        api_url: str = "https://api.github.com",
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not app_id.isdigit() or not installation_id.isdigit():
            raise ValueError("GitHub App and installation IDs must be numeric")
        self._app_id = app_id
        self._installation_id = installation_id
        self._key = private_key
        self._api = api_url.rstrip("/")
        self._transport = transport
        self._clock = clock
        self._token: str | None = None
        self._token_expires = 0.0
        self._check_ids: dict[tuple[str, str], str] = {}

    @classmethod
    def from_settings(
        cls, settings: IntegrationSettings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> "GitHubAppCheckRunPublisher":
        config = require("github_app", settings.github_app)
        try:
            pem = config.private_key_path.read_text(encoding="ascii")
        except OSError:
            raise EnvironmentUnavailableError("GITHUB_PRIVATE_KEY_PATH could not be read") from None
        return cls(
            app_id=config.app_id,
            installation_id=config.installation_id,
            private_key=parse_rsa_private_key(pem),
            api_url=config.api_url,
            transport=transport,
        )

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._api,
            transport=self._transport,
            timeout=15.0,
            follow_redirects=False,
            trust_env=False,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "gauntlet-checks",
            },
        )

    async def _installation_token(self, client: httpx.AsyncClient) -> str:
        if self._token and self._clock() < self._token_expires - 120:
            return self._token
        jwt = app_jwt(self._app_id, self._key, now=int(self._clock()))
        response = await client.post(
            f"/app/installations/{self._installation_id}/access_tokens",
            headers={"Authorization": f"Bearer {jwt}"},
            json={"permissions": {"checks": "write"}},
        )
        if response.status_code != 201:
            raise EnvironmentUnavailableError(
                f"GitHub installation token request failed (HTTP {response.status_code})"
            )
        body = response.json()
        token = body.get("token") if isinstance(body, dict) else None
        if not isinstance(token, str) or not token:
            raise EnvironmentUnavailableError("GitHub returned no installation token")
        self._token = token
        self._token_expires = self._clock() + 3600
        return token

    async def publish(
        self, repository_full_name: str, head_sha: str, external_id: str, report: CheckRunReport
    ) -> str:
        if not _REPO.fullmatch(repository_full_name) or ".." in repository_full_name:
            raise ValueError("repository name is invalid")
        if not _SHA.fullmatch(head_sha):
            raise ValueError("head SHA must be a full 40-character commit SHA")
        if not _EXTERNAL_ID.fullmatch(external_id):
            raise ValueError("external ID is invalid")
        owner, repo = (quote(part, safe="") for part in repository_full_name.split("/"))
        body: dict[str, object] = {
            "name": report.name,
            "head_sha": head_sha,
            "external_id": external_id,
            "status": "completed",
            "conclusion": report.conclusion,
            "output": {"title": report.title[:255], "summary": report.summary[:_MAX_SUMMARY]},
        }
        if report.details_url:
            body["details_url"] = report.details_url
        async with self._client() as client:
            token = await self._installation_token(client)
            auth = {"Authorization": f"token {token}"}
            existing = self._check_ids.get((repository_full_name, external_id))
            if existing is None:
                existing = await self._find_existing(
                    client, auth, owner, repo, head_sha, report, external_id
                )
            if existing is not None:
                response = await client.patch(
                    f"/repos/{owner}/{repo}/check-runs/{existing}", headers=auth, json=body
                )
                expected = 200
            else:
                response = await client.post(
                    f"/repos/{owner}/{repo}/check-runs", headers=auth, json=body
                )
                expected = 201
        if response.status_code != expected:
            raise EnvironmentUnavailableError(
                f"GitHub check run publish failed (HTTP {response.status_code})"
            )
        payload = response.json()
        check_id = payload.get("id") if isinstance(payload, dict) else None
        if not isinstance(check_id, int):
            raise EnvironmentUnavailableError("GitHub returned no check run ID")
        self._check_ids[(repository_full_name, external_id)] = str(check_id)
        return str(check_id)

    async def _find_existing(
        self,
        client: httpx.AsyncClient,
        auth: Mapping[str, str],
        owner: str,
        repo: str,
        head_sha: str,
        report: CheckRunReport,
        external_id: str,
    ) -> str | None:
        response = await client.get(
            f"/repos/{owner}/{repo}/commits/{head_sha}/check-runs",
            headers=dict(auth),
            params={"check_name": report.name, "filter": "latest"},
        )
        if response.status_code != 200:
            return None
        payload = response.json()
        runs = payload.get("check_runs") if isinstance(payload, dict) else None
        if not isinstance(runs, list):
            return None
        for run in runs:
            if (
                isinstance(run, dict)
                and run.get("external_id") == external_id
                and isinstance(run.get("id"), int)
            ):
                return str(run["id"])
        return None


def load_private_key(path: Path) -> RsaPrivateKey:
    return parse_rsa_private_key(path.read_text(encoding="ascii"))
