"""Settings module: names-only errors, placeholders unset, masked secrets, Anchor proxy flag."""

import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from gauntlet.execution.provider_smoke_config import preflight
from gauntlet.integrations.anchor.sdk import WEAK_ISOLATION_WARNING, SdkAnchorRuntime
from gauntlet.settings import (
    MissingSettingError,
    Secret,
    SettingsError,
    load_settings,
    require,
    require_live,
)

SECRET_VALUE = "synthetic-test-value-0123456789"


def test_empty_environment_loads_with_everything_unset() -> None:
    settings = load_settings({})
    assert settings.core.run_live_integrations is False
    assert settings.model_provider == "scripted"
    assert settings.readiness()["arize"] == "unset"
    with pytest.raises(MissingSettingError, match="missing ARIZE_API_KEY, ARIZE_SPACE_ID"):
        require("arize", settings.arize)
    with pytest.raises(MissingSettingError, match="RUN_LIVE_INTEGRATIONS=1"):
        require_live(settings)


def test_env_example_placeholders_count_as_unset() -> None:
    example = Path(__file__).resolve().parents[3] / ".env.example"
    environ = {}
    for line in example.read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            environ[key] = value
    settings = load_settings(environ)
    configured = {k: v for k, v in settings.readiness().items() if v == "configured"}
    assert configured == {}


def test_secrets_never_print() -> None:
    settings = load_settings({"ARIZE_API_KEY": SECRET_VALUE, "ARIZE_SPACE_ID": SECRET_VALUE})
    assert settings.arize is not None
    assert SECRET_VALUE not in repr(settings)
    assert SECRET_VALUE not in str(settings.readiness())
    assert settings.arize.api_key.reveal() == SECRET_VALUE
    assert "x" not in repr(Secret("x"))


def test_partial_section_is_an_error_naming_keys_only() -> None:
    with pytest.raises(SettingsError) as raised:
        load_settings({"DAYTONA_API_KEY": SECRET_VALUE})
    assert "DAYTONA_API_URL" in str(raised.value)
    assert SECRET_VALUE not in str(raised.value)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("GAUNTLET_MAX_RUN_SECONDS", "abc"),
        ("RUN_LIVE_INTEGRATIONS", "maybe"),
        ("GAUNTLET_MODEL_PROVIDER", "openai-x"),
        ("GAUNTLET_ANCHOR_REQUIRE_PROXY", "2"),
    ],
)
def test_invalid_values_rejected_without_echoing_value(key: str, value: str) -> None:
    with pytest.raises(SettingsError) as raised:
        load_settings({key: value})
    assert key in str(raised.value)
    assert value not in str(raised.value)


def test_anchor_requires_proxy_by_default() -> None:
    with pytest.raises(MissingSettingError, match="ANCHOR_PROXY_SERVER"):
        load_settings({"ANCHOR_API_KEY": SECRET_VALUE})
    settings = load_settings({"ANCHOR_API_KEY": SECRET_VALUE, "GAUNTLET_ANCHOR_REQUIRE_PROXY": "0"})
    assert settings.anchor is not None and settings.anchor.proxy is None
    assert settings.readiness()["anchor"] == "configured_without_egress_proxy"


def test_bedrock_selectable_and_github_ids_numeric() -> None:
    settings = load_settings(
        {"GAUNTLET_MODEL_PROVIDER": "bedrock", "AWS_REGION": "us-east-1", "BEDROCK_MODEL_ID": "m"}
    )
    assert settings.model_provider == "bedrock" and settings.bedrock is not None
    with pytest.raises(SettingsError, match="GITHUB_APP_ID must be numeric"):
        load_settings(
            {
                "GITHUB_APP_ID": "abc",
                "GITHUB_INSTALLATION_ID": "1",
                "GITHUB_PRIVATE_KEY_PATH": "/k.pem",
                "GITHUB_WEBHOOK_SECRET": SECRET_VALUE,
            }
        )


def test_reviewer_tokens_parse_and_reject_short() -> None:
    settings = load_settings({"GAUNTLET_REVIEWER_TOKENS": f"alice:{SECRET_VALUE}"})
    assert settings.reviewers is not None
    assert settings.reviewers.tokens[0][0] == "alice"
    with pytest.raises(SettingsError):
        load_settings({"GAUNTLET_REVIEWER_TOKENS": "alice:short"})


class _Client:
    def __init__(self) -> None:
        self.config: dict[str, object] | None = None
        self.sessions = self
        self.browser = self

    async def create_session(self, **kwargs: object) -> SimpleNamespace:
        self.config = kwargs
        return SimpleNamespace(data=SimpleNamespace(id="anchor-session-9"))

    async def connect(self, session_id: str) -> "_Client":
        return self

    async def __aenter__(self) -> object:
        return object()


def test_anchor_without_proxy_warns_and_records_isolation(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("RUN_LIVE_INTEGRATIONS", "1")
    client = _Client()
    with caplog.at_level(logging.WARNING, logger="gauntlet.integrations.anchor"):
        runtime = SdkAnchorRuntime(
            client, proxy_server=None, proxy_username=None, proxy_password=None, require_proxy=False
        )
        connection = asyncio.run(runtime.open())
    assert WEAK_ISOLATION_WARNING in caplog.text
    assert client.config is not None
    assert client.config["session"] == {"recording": {"active": True}}
    assert runtime.egress_isolation == "none_weaker_isolation"
    assert connection.egress_isolation == "none_weaker_isolation"
    assert connection.recording_id == "anchor-session-9"


def test_anchor_still_refuses_missing_proxy_when_required() -> None:
    with pytest.raises(ValueError, match="egress proxy"):
        SdkAnchorRuntime(_Client(), proxy_server=None, proxy_username=None, proxy_password=None)


def test_preflight_drops_proxy_keys_only_when_flag_off() -> None:
    base = {"RUN_LIVE_INTEGRATIONS": "1", "GAUNTLET_ALLOWED_TARGET_IDS": "cartwheel-fixture"}
    strict = preflight(base, spend_authorized=True, registration_present=True)
    assert "ANCHOR_PROXY_SERVER" in strict["missing"]
    relaxed = preflight(
        {**base, "GAUNTLET_ANCHOR_REQUIRE_PROXY": "0"},
        spend_authorized=True,
        registration_present=True,
    )
    assert "ANCHOR_PROXY_SERVER" not in relaxed["missing"]
    assert relaxed["anchor_egress_isolation"] == "none_weaker_isolation"
