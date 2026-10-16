"""Pinned Anchor 1.0.1 SDK boundary; import the SDK only on explicit setup."""

import os
from typing import Any
from urllib.parse import urlsplit

from gauntlet.ports.errors import EnvironmentUnavailableError


class SdkAnchorConnection:
    def __init__(self, client: Any, session_id: str, manager: Any, browser: Any) -> None:  # noqa: ANN401
        self.browser = browser
        self._client = client
        self._session_id = session_id
        self._manager = manager
        self._disconnected = False
        self._deleted = False

    async def close(self) -> None:
        if not self._disconnected:
            await self._manager.__aexit__(None, None, None)
            self._disconnected = True
        if not self._deleted:
            await self._client.sessions.delete_session(self._session_id, timeout=15)
            self._deleted = True


class SdkAnchorRuntime:
    def __init__(
        self,
        client: Any,  # noqa: ANN401 - optional provider boundary
        *,
        proxy_server: str,
        proxy_username: str,
        proxy_password: str,
    ) -> None:
        parsed = urlsplit(proxy_server)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.port is None
            or proxy_server != f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
            or not proxy_username
            or not proxy_password
        ):
            raise ValueError("explicit custom egress proxy configuration is required")
        self._client = client
        self._pending_cleanup: set[str] = set()
        self._proxy = {
            "type": "custom",
            "server": proxy_server,
            "username": proxy_username,
            "password": proxy_password,
            "active": True,
        }

    @property
    def pending_cleanup_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._pending_cleanup))

    async def retry_pending_cleanup(self) -> None:
        for session_id in self.pending_cleanup_ids:
            try:
                await self._client.sessions.delete_session(session_id, timeout=15)
            except Exception as exc:
                raise EnvironmentUnavailableError("Anchor session cleanup failed") from exc
            self._pending_cleanup.discard(session_id)

    @classmethod
    def from_credentials(
        cls,
        *,
        api_key: str,
        proxy_server: str,
        proxy_username: str,
        proxy_password: str,
    ) -> "SdkAnchorRuntime":
        if not api_key:
            raise ValueError("explicit Anchor API key is required")
        from anchorbrowser import AsyncAnchorbrowser

        return cls(
            AsyncAnchorbrowser(api_key=api_key, max_retries=0, timeout=30),
            proxy_server=proxy_server,
            proxy_username=proxy_username,
            proxy_password=proxy_password,
        )

    async def open(self) -> SdkAnchorConnection:
        if os.environ.get("RUN_LIVE_INTEGRATIONS") != "1":
            raise EnvironmentUnavailableError("live Anchor integration is not enabled")
        try:
            result = await self._client.sessions.create_session(
                session={"recording": {"active": True}, "proxy": self._proxy},
                browser={"headless": {"active": True}, "popup_blocker": {"active": True}},
                timeout=30,
            )
        except Exception as exc:
            raise EnvironmentUnavailableError("Anchor session creation failed") from exc
        session_id = getattr(getattr(result, "data", None), "id", None)
        if not isinstance(session_id, str) or not session_id:
            raise EnvironmentUnavailableError("Anchor session ID was not returned")
        try:
            manager = await self._client.browser.connect(session_id)
            browser = await manager.__aenter__()
        except BaseException as exc:
            try:
                await self._client.sessions.delete_session(session_id, timeout=15)
            except Exception:
                self._pending_cleanup.add(session_id)
            if isinstance(exc, KeyboardInterrupt | SystemExit):
                raise
            if isinstance(exc, Exception):
                raise EnvironmentUnavailableError("Anchor CDP connection failed") from exc
            raise
        return SdkAnchorConnection(self._client, session_id, manager, browser)

    async def close(self) -> None:
        await self._client.close()
