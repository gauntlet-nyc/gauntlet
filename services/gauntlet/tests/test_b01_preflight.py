"""Local readiness must not invoke providers, disclose keys, or claim live success."""

import importlib.metadata
import json
import runpy
import socket
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast

import pytest

PROBE = Path(__file__).resolve().parents[3] / "scripts/probe_sdk_inventory.py"
Preflight = Callable[..., dict[str, object]]


def preflight() -> Preflight:
    return cast(Preflight, runpy.run_path(str(PROBE))["ui_preflight"])


def configured() -> dict[str, str]:
    return {
        "RUN_LIVE_INTEGRATIONS": "1",
        "DAYTONA_API_KEY": "synthetic-daytona-secret",
        "ANCHOR_API_KEY": "synthetic-anchor-secret",
        "GAUNTLET_ALLOWED_TARGET_IDS": "cartwheel-fixture",
    }


def test_preflight_stays_not_tested_even_with_local_prerequisites(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def version(package: str) -> str:
        return "1.2.3"

    def deny_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("preflight attempted network access")

    probe = preflight()
    monkeypatch.setattr(importlib.metadata, "version", version)
    monkeypatch.setattr(socket.socket, "connect", deny_network)
    result = probe(environment=configured())
    assert result["local_prerequisites_present"] is True
    assert result["status"] == "not_tested"
    assert result["scope"] == "local_prerequisites_only"
    serialized = json.dumps(result)
    assert "synthetic-daytona-secret" not in serialized
    assert "synthetic-anchor-secret" not in serialized


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("RUN_LIVE_INTEGRATIONS", "0"),
        ("DAYTONA_API_KEY", "REPLACE_ME"),
        ("ANCHOR_API_KEY", "  "),
        ("GAUNTLET_ALLOWED_TARGET_IDS", "cartwheel-fixture-impostor"),
    ],
)
def test_missing_configuration_blocks_readiness(
    monkeypatch: pytest.MonkeyPatch, key: str, value: str
) -> None:
    def version(package: str) -> str:
        return "1.2.3"

    monkeypatch.setattr(importlib.metadata, "version", version)
    environment = configured()
    environment[key] = value
    result = preflight()(environment=environment)
    assert result["local_prerequisites_present"] is False
    assert result["status"] == "not_tested"


def test_missing_sdk_blocks_readiness(monkeypatch: pytest.MonkeyPatch) -> None:
    def version(package: str) -> str:
        if package == "anchorbrowser":
            raise importlib.metadata.PackageNotFoundError(package)
        return "1.2.3"

    monkeypatch.setattr(importlib.metadata, "version", version)
    result = preflight()(environment=configured())
    assert result["local_prerequisites_present"] is False
    assert result["package_versions"] == {
        "daytona": "1.2.3",
        "anchorbrowser": None,
        "playwright": "1.2.3",
    }


def test_preflight_cli_missing_configuration_returns_machine_readable_failure() -> None:
    environment: Mapping[str, str] = {}
    result = subprocess.run(
        [sys.executable, str(PROBE), "--ui-preflight"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report["status"] == "not_tested"
    assert report["local_prerequisites_present"] is False
