"""Frozen local execution must preserve the reviewed plan and fail before browser startup."""

import asyncio
import importlib.util
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import pytest
from fakes import StaticTargetCatalog

from gauntlet.contracts import ChangeRequest
from gauntlet.integrations.local_gate_diagnostic import freeze_diagnostic_plan
from gauntlet.planning import FrozenPlan
from gauntlet.ports.errors import EnvironmentUnavailableError

ROOT = Path(__file__).resolve().parents[3]


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def inputs(tmp_path: Path) -> tuple[Path, FrozenPlan]:
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
    frozen = asyncio.run(freeze_diagnostic_plan(repo, change, targets=StaticTargetCatalog())).frozen
    return repo, frozen


def test_empty_plan_rejected_before_browser(
    inputs: tuple[Path, FrozenPlan], tmp_path: Path
) -> None:
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


def test_receipt_failure_precedes_browser(
    inputs: tuple[Path, FrozenPlan], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, frozen = inputs
    probe = load("probe_p1_frozen_gate")
    calls = []

    async def reject(origin: str, sha: str) -> None:
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


def test_checkout_mismatch_precedes_receipt(
    inputs: tuple[Path, FrozenPlan], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, frozen = inputs
    probe = load("probe_p1_frozen_gate")

    async def unexpected(*args: object) -> None:
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


def test_non_ui_rejected_before_receipt(inputs: tuple[Path, FrozenPlan], tmp_path: Path) -> None:
    repo, frozen = inputs
    probe = load("probe_p1_frozen_gate")
    attack = frozen.attacks[0].model_copy(update={"worker_kind": "ai"})
    with pytest.raises(ValueError, match="UI"):
        asyncio.run(
            probe.probe(
                replace(frozen, attacks=(attack,)),
                "head",
                "http://127.0.0.1:3100",
                tmp_path / "chrome",
                repo,
                tmp_path / "out",
            )
        )


def test_each_attack_and_subject_preserved_twice(inputs: tuple[Path, FrozenPlan]) -> None:
    import json
    from unittest.mock import AsyncMock

    from gauntlet.contracts import Observation, OracleVerdict
    from gauntlet.ports.sandbox import EnvironmentHandle

    _, frozen = inputs
    probe = load("probe_p1_frozen_gate")
    environment = EnvironmentHandle(
        environment_id="local-env",
        target_id=frozen.change.target_id,
        source_sha=frozen.change.head_sha,
        fixture_id=frozen.change.fixture_id,
        fixture_checksum="a" * 64,
        preview_origin="http://127.0.0.1:3100",
    )
    worker = AsyncMock()
    oracle = AsyncMock()
    worker.run.return_value = Observation.model_validate_json(
        (ROOT / "docs/contracts/examples/observation.v1.json").read_text()
    )
    oracle.evaluate.return_value = OracleVerdict.model_validate(
        json.loads((ROOT / "docs/contracts/examples/oracle-verdict.v1.json").read_text())
    )
    result = asyncio.run(probe.run_attacks(frozen, environment, worker, oracle))
    assert len(result) == 2
    subjects = []
    for index, call in enumerate(worker.run.call_args_list):
        attack, actual_environment, subject = call.args
        assert attack is frozen.attacks[0]
        assert actual_environment is environment
        assert subject.run_id == frozen.run_id
        assert subject.source_sha == environment.source_sha
        assert subject.environment_id == environment.environment_id
        assert oracle.evaluate.call_args_list[index].args == (
            attack.oracle_ids[0],
            attack,
            worker.run.return_value,
            subject,
        )
        subjects.append(subject)
    assert subjects[0].attempt_id != subjects[1].attempt_id
    assert subjects[0].observation_id != subjects[1].observation_id
    assert result[0]["verdicts"][0]["outcome"] == "fail"
