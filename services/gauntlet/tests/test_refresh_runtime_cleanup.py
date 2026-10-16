"""Gate composition owns provider clients even if later setup fails."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gauntlet import composition
from gauntlet.execution import provider_smoke_config
from gauntlet.integrations.anchor.sdk import SdkAnchorRuntime
from gauntlet.integrations.daytona.sdk import SdkDaytonaRuntime
from gauntlet.settings import Settings


@pytest.mark.parametrize("failure", [None, "error", "cancel"])
def test_gate_closes_owned_provider_clients(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str | None
) -> None:
    closed: list[str] = []

    async def close_daytona() -> None:
        closed.append("daytona")

    async def close_anchor() -> None:
        closed.append("anchor")

    daytona = SimpleNamespace(close=AsyncMock(side_effect=close_daytona))
    anchor = SimpleNamespace(close=AsyncMock(side_effect=close_anchor))
    monkeypatch.setattr(SdkDaytonaRuntime, "from_credentials", lambda **kwargs: daytona)
    monkeypatch.setattr(SdkAnchorRuntime, "without_proxy", lambda **kwargs: anchor)
    target = composition.GateTarget.cartwheel(tmp_path)
    registered = SimpleNamespace(target_id=target.target_id, preview_domain_suffix=".example.test")
    monkeypatch.setattr(
        provider_smoke_config, "load_registration", lambda *args: (None, registered)
    )
    settings = Settings.from_env(
        {
            "RUN_LIVE_INTEGRATIONS": "1",
            "DAYTONA_API_KEY": "synthetic-daytona-key",
            "DAYTONA_API_URL": "https://daytona.example.test/api",
            "DAYTONA_TARGET": "us",
            "GAUNTLET_DAYTONA_REGISTRATION": "synthetic-registration.json",
            "ANCHOR_API_KEY": "synthetic-anchor-key",
            "GAUNTLET_ANCHOR_REQUIRE_PROXY": "0",
        }
    )
    if failure:

        async def fail_browser(*args: object, **kwargs: object) -> None:
            if failure == "cancel":
                raise asyncio.CancelledError()
            raise RuntimeError("browser setup failed")

        monkeypatch.setattr(composition, "_build_browser", fail_browser)

    async def scenario() -> None:
        runtime = await composition.build_gate(
            settings,
            target,
            model="scripted",
            sandbox="daytona",
            browser="anchor",
            artifact_root=tmp_path / "artifacts",
        )
        await runtime.aclose()
        await runtime.aclose()

    if failure:
        error = asyncio.CancelledError if failure == "cancel" else RuntimeError
        with pytest.raises(error):
            asyncio.run(scenario())
        assert closed == ["daytona"]
    else:
        asyncio.run(scenario())
        assert closed == ["anchor", "daytona"]
