"""Frozen local execution must preserve the reviewed plan and fail before browser startup."""

import asyncio
import importlib.util
from dataclasses import replace
from pathlib import Path

import pytest

from gauntlet.contracts import ChangeRequest
from gauntlet.integrations.local_gate_diagnostic import freeze_diagnostic_plan
from gauntlet.ports.errors import EnvironmentUnavailableError

ROOT = Path(__file__).resolve().parents[3]


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def inputs(tmp_path):
    builder = load("build_cartwheel_fixture")
    repo = tmp_path / "fixture"
    builder.build(repo)
    import json

    manifest = json.loads((ROOT / "apps/cartwheel/fixture-manifest.v1.json").read_text())
    change = ChangeRequest(
        repository_id="cartwheel",
        base_sha=manifest["git_refs"]["base_sha"],
        head_sha=manifest["git_refs"]["head_sha"],
        target_id=manifest["target_id"],
        fixture_id=manifest["fixture_id"],
        max_cost_usd_cents=500,
    )
    frozen = asyncio.run(freeze_diagnostic_plan(repo, change)).frozen
    return repo, frozen


def test_empty_plan_rejected_before_browser(inputs, tmp_path):
    repo, frozen = inputs
    probe = load("probe_p1_frozen_gate")
    with pytest.raises(ValueError):
        asyncio.run(
            probe.probe(
                replace(frozen, attacks=()),
                "head",
                "http://127.0.0.1:3100",
                tmp_path / "missing-chrome",
                repo,
                tmp_path / "out",
            )
        )
    assert not (tmp_path / "out").exists()


def test_receipt_failure_precedes_browser(inputs, tmp_path, monkeypatch):
    repo, frozen = inputs
    probe = load("probe_p1_frozen_gate")
    calls = []

    async def reject(origin, sha):
        calls.append((origin, sha))
        raise EnvironmentUnavailableError("receipt mismatch")

    monkeypatch.setattr(probe, "verify_fixture_build_receipt", reject)
    with pytest.raises(EnvironmentUnavailableError, match="receipt"):
        asyncio.run(
            probe.probe(
                frozen,
                "head",
                "http://127.0.0.1:3100",
                tmp_path / "missing-chrome",
                repo,
                tmp_path / "out",
            )
        )
    assert calls == [("http://127.0.0.1:3100", frozen.change.head_sha)]
    assert not (tmp_path / "out").exists()


def test_checkout_mismatch_precedes_receipt(inputs, tmp_path, monkeypatch):
    repo, frozen = inputs
    probe = load("probe_p1_frozen_gate")

    async def unexpected(*args):
        raise AssertionError("receipt requested for wrong checkout")

    monkeypatch.setattr(probe, "verify_fixture_build_receipt", unexpected)
    with pytest.raises(ValueError, match="checkout"):
        asyncio.run(
            probe.probe(
                frozen,
                "base",
                "http://127.0.0.1:3100",
                tmp_path / "missing-chrome",
                repo,
                tmp_path / "out",
            )
        )
