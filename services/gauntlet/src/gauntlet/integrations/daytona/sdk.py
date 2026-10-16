"""Optional Daytona 0.224.1 SDK boundary; import only when used.

No client is created or provider call made by importing this module. The
caller supplies credentials and owns closing this client after all sandboxes.
"""

import os
from typing import Any

import httpx

from gauntlet.ports.errors import EnvironmentUnavailableError

from .provider import DaytonaSandbox


class SdkSandbox:
    def __init__(self, sandbox: Any) -> None:  # noqa: ANN401 - optional provider boundary
        self._sandbox = sandbox
        self.id: str = sandbox.id

    async def checkout_sha(self, repo_path: str) -> str:
        result = await self._sandbox.process.exec("git rev-parse HEAD", cwd=repo_path, timeout=15)
        if result.exit_code != 0:
            raise EnvironmentUnavailableError("Daytona checkout revision could not be read")
        return str(result.result).strip()

    async def read_file(self, path: str) -> bytes:
        content = await self._sandbox.fs.download_file(path, timeout=30)
        if not isinstance(content, bytes):
            raise EnvironmentUnavailableError("Daytona fixture state was not returned as bytes")
        return content

    async def start_cartwheel(self, repo_path: str, port: int) -> None:
        """Start the registered Cartwheel build after provider source attestation."""
        if type(port) is not int or not 1 <= port <= 65535:
            raise EnvironmentUnavailableError("Daytona registered startup port is invalid")
        command = (
            "test -s .next/BUILD_ID && test -x ./node_modules/.bin/next && "
            f"(nohup ./node_modules/.bin/next start -p {port} "
            ">/tmp/gauntlet-cartwheel-start.log 2>&1 </dev/null &)"
        )
        result = await self._sandbox.process.exec(command, cwd=repo_path, timeout=20)
        if result.exit_code != 0:
            raise EnvironmentUnavailableError("Daytona registered startup failed")

    async def signed_preview_origin(self, port: int, expires_in_seconds: int) -> str:
        preview = await self._sandbox.create_signed_preview_url(
            port, expires_in_seconds=expires_in_seconds, request_timeout=15
        )
        return str(preview.url)


class SdkDaytonaRuntime:
    def __init__(self, client: Any) -> None:  # noqa: ANN401 - optional provider boundary
        self._client = client

    @classmethod
    def from_credentials(cls, *, api_key: str, api_url: str, target: str) -> "SdkDaytonaRuntime":
        if not api_key or not api_url.startswith("https://") or not target:
            raise ValueError("explicit Daytona API key, HTTPS API URL and target are required")
        from daytona import AsyncDaytona, DaytonaConfig

        return cls(AsyncDaytona(DaytonaConfig(api_key=api_key, api_url=api_url, target=target)))

    async def create(self, snapshot: str, timeout: float) -> SdkSandbox:
        if os.environ.get("RUN_LIVE_INTEGRATIONS") != "1":
            raise EnvironmentUnavailableError("live Daytona integration is not enabled")
        from daytona import CreateSandboxFromSnapshotParams

        params = CreateSandboxFromSnapshotParams(
            snapshot=snapshot,
            public=False,
            network_block_all=True,
        )
        return SdkSandbox(await self._client.create(params, timeout=timeout))

    async def delete(self, sandbox: DaytonaSandbox, timeout: float) -> None:
        if not isinstance(sandbox, SdkSandbox):
            raise EnvironmentUnavailableError("Daytona sandbox does not belong to this SDK runtime")
        await self._client.delete(sandbox._sandbox, timeout=timeout, wait=True)

    async def close(self) -> None:
        await self._client.close()


class HttpxHealthProbe:
    async def check(self, origin: str, path: str) -> bool:
        async with httpx.AsyncClient(timeout=5, follow_redirects=False, trust_env=False) as client:
            try:
                response = await client.get(origin + path)
            except httpx.HTTPError:
                return False
        return response.status_code == 200
