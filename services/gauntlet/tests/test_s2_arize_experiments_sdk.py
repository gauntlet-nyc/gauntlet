"""Arize Experiments SDK publisher (offline: fake client; SDK field types when installed)."""

import asyncio
from types import SimpleNamespace

import pytest

from gauntlet.integrations.arize.experiments_sdk import (
    ArizeExperimentPublisher,
    RecallExperimentRow,
    experiment_runs,
)
from gauntlet.ports.errors import EnvironmentUnavailableError
from gauntlet.settings import load_settings

ROWS = [
    RecallExperimentRow(
        "dec-001", "rp-c1", "matched", "refund", "rp-f1", "different", "deny", True, True, "tainted"
    ),
    RecallExperimentRow(
        "dec-004",
        "rp-c4",
        "matched",
        "refund",
        "rp-f4",
        "matched",
        "refund",
        True,
        False,
        "cleared",
    ),
    RecallExperimentRow(
        "dec-007",
        "rp-c7",
        "not_replayable",
        None,
        "rp-f7",
        "not_replayable",
        None,
        False,
        False,
        "not_replayable",
    ),
]


def test_runs_carry_ids_and_verdicts_only() -> None:
    runs = experiment_runs(ROWS)
    assert runs[0]["output"] == "deny" and runs[0]["material_score"] == 1.0
    assert (
        runs[2]["output"] == "<not_replayable>" and runs[2]["control_action"] == "<not_replayable>"
    )
    assert {r["verdict"] for r in runs} == {"tainted", "cleared", "not_replayable"}


def test_publish_with_real_sdk_types_and_fake_client() -> None:
    pytest.importorskip("arize")
    calls: list[dict[str, object]] = []

    class Experiments:
        def create(self, **kwargs: object) -> SimpleNamespace:
            calls.append(kwargs)
            return SimpleNamespace(id="exp-123")

    publisher = ArizeExperimentPublisher(SimpleNamespace(experiments=Experiments()), space="sp")
    assert asyncio.run(publisher.publish("recall-kb-117", ROWS)) == "exp-123"
    call = calls[0]
    assert call["space"] == "sp" and call["name"] == "recall-kb-117"
    assert len(call["experiment_runs"]) == 3  # type: ignore[arg-type]
    assert call["task_fields"].output == "output"


def test_publish_errors_are_sanitized_and_bounded() -> None:
    pytest.importorskip("arize")

    class Experiments:
        def create(self, **kwargs: object) -> None:
            raise RuntimeError("401 api_key=secret-value")

    publisher = ArizeExperimentPublisher(SimpleNamespace(experiments=Experiments()), space="sp")
    with pytest.raises(EnvironmentUnavailableError) as raised:
        asyncio.run(publisher.publish("x", ROWS))
    assert "secret-value" not in str(raised.value)
    with pytest.raises(ValueError):
        asyncio.run(publisher.publish("x", []))


def test_needs_live_flag_and_keys() -> None:
    with pytest.raises(EnvironmentUnavailableError, match="RUN_LIVE_INTEGRATIONS"):
        ArizeExperimentPublisher.from_settings(load_settings({}))
