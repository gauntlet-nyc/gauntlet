"""GitHub App adapter: App JWT (RS256) -> installation token -> check runs. Checks-only.

No new dependency: RS256 is RSASSA-PKCS1-v1_5 over SHA-256 implemented with Python
integers (the key file is read from `GITHUB_PRIVATE_KEY_PATH`, never from the repo or a
prompt). Python big-int arithmetic is not constant-time; acceptable for this dev-grade
signer running on our own host, but a production deployment should use a vetted library.

The publisher only creates/updates check runs. It never pushes, comments, approves or
merges, and the installation token is requested with `checks: write` only.
"""

import base64
import hashlib
import json
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from urllib.parse import quote

import httpx

from gauntlet.ports.code_host import CheckRunReport
from gauntlet.ports.errors import EnvironmentUnavailableError
from gauntlet.settings import IntegrationSettings, require

_SHA256_DIGEST_INFO: Final = bytes.fromhex("3031300d060960864801650304020105000420")
_REPO: Final = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_SHA: Final = re.compile(r"^[0-9a-f]{40}$")
_EXTERNAL_ID: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_SUMMARY: Final = 65_000


# ---- minimal DER reader for RSA private keys (PKCS#1 and PKCS#8) ----


def _der_read(data: bytes, offset: int) -> tuple[int, bytes, int]:
    tag = data[offset]
    length = data[offset + 1]
    offset += 2
    if length & 0x80:
        count = length & 0x7F
        if count == 0 or count > 4:
            raise ValueError("unsupported DER length")
        length = int.from_bytes(data[offset : offset + count], "big")
        offset += count
    end = offset + length
    if end > len(data):
        raise ValueError("truncated DER")
    return tag, data[offset:end], end


def _der_sequence(data: bytes) -> list[tuple[int, bytes]]:
    items: list[tuple[int, bytes]] = []
    offset = 0
    while offset < len(data):
        tag, value, offset = _der_read(data, offset)
        items.append((tag, value))
    return items


@dataclass(frozen=True)
class RsaPrivateKey:
    n: int
    e: int
    d: int
    p: int
    q: int
    dp: int
    dq: int
    qinv: int

    def __repr__(self) -> str:
        return f"RsaPrivateKey(bits={self.n.bit_length()})"

    @property
    def size_bytes(self) -> int:
        return (self.n.bit_length() + 7) // 8

    def sign_sha256(self, message: bytes) -> bytes:
        digest_info = _SHA256_DIGEST_INFO + hashlib.sha256(message).digest()
        k = self.size_bytes
        if k < len(digest_info) + 11:
            raise ValueError("RSA key too small")
        encoded = b"\x00\x01" + b"\xff" * (k - len(digest_info) - 3) + b"\x00" + digest_info
        m = int.from_bytes(encoded, "big")
        # CRT signing, then verify before release (guards against fault/key errors).
        s1 = pow(m, self.dp, self.p)
        s2 = pow(m, self.dq, self.q)
        h = (self.qinv * (s1 - s2)) % self.p
        s = s2 + h * self.q
        if pow(s, self.e, self.n) != m:
            raise ValueError("RSA signature self-check failed")
        return s.to_bytes(k, "big")


def parse_rsa_private_key(pem: str, *, min_bits: int = 2048) -> RsaPrivateKey:
    """Accept `RSA PRIVATE KEY` (PKCS#1, GitHub's download) or `PRIVATE KEY` (PKCS#8)."""
    match = re.search(
        r"-----BEGIN (RSA )?PRIVATE KEY-----([A-Za-z0-9+/=\s]+)-----END (RSA )?PRIVATE KEY-----",
        pem,
    )
    if match is None:
        raise ValueError("GitHub App private key is not an unencrypted RSA PEM")
    der = base64.b64decode("".join(match.group(2).split()))
    tag, body, _ = _der_read(der, 0)
    if tag != 0x30:
        raise ValueError("private key is not a DER sequence")
    items = _der_sequence(body)
    if match.group(1) is None:  # PKCS#8: version, algorithm, OCTET STRING(PKCS#1)
        if len(items) < 3 or items[2][0] != 0x04:
            raise ValueError("unsupported PKCS#8 private key")
        if bytes.fromhex("2a864886f70d010101") not in items[1][1]:
            raise ValueError("PKCS#8 key is not RSA")
        tag, body, _ = _der_read(items[2][1], 0)
        items = _der_sequence(body)
    integers = [int.from_bytes(value, "big") for tag, value in items if tag == 0x02]
    if len(integers) < 9 or integers[0] != 0:
        raise ValueError("unsupported RSA private key structure")
    _, n, e, d, p, q, dp, dq, qinv = integers[:9]
    if p * q != n or n.bit_length() < min_bits:
        raise ValueError("RSA key is inconsistent or too small")
    return RsaPrivateKey(n=n, e=e, d=d, p=p, q=q, dp=dp, dq=dq, qinv=qinv)


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
