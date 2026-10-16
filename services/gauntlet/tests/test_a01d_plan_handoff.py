"""Frozen handoffs bind to independently trusted inputs, never their own claimed hash."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from conftest import DemoRepo
from test_planning import inspect, run_use_case, ui_attack

from gauntlet.planning import FrozenPlan
from gauntlet.planning.handoff import (
    load_frozen_plan,
    require_executable_plan,
    serialize_frozen_plan,
)

PROMPT_HASH = "a" * 64


@pytest.fixture
def plan(demo_repo: DemoRepo) -> FrozenPlan:
    impact = inspect(demo_repo, demo_repo.ui_head)
    return run_use_case(demo_repo, demo_repo.ui_head, {"attacks": [ui_attack(impact)]})[0]


def load(raw: str, plan: FrozenPlan, **overrides: object) -> FrozenPlan:
    expected = dict(
        expected_change=plan.change,
        expected_plan_hash=plan.plan_hash,
        expected_model_id=plan.model_id,
        expected_prompt_sha256=PROMPT_HASH,
        expected_run_id=plan.run_id,
    )
    expected.update(overrides)
    return load_frozen_plan(raw, **expected)


def test_round_trip(plan: FrozenPlan) -> None:
    raw = serialize_frozen_plan(plan, prompt_sha256=PROMPT_HASH)
    restored = load(raw, plan)
    assert restored == plan
    assert require_executable_plan(restored) == restored


@pytest.mark.parametrize(
    "field", ["attack", "change", "impact", "hash", "extra", "nested_extra", "version", "coercion"]
)
def test_corruption_rejected(plan: FrozenPlan, field: str) -> None:
    doc = json.loads(serialize_frozen_plan(plan, prompt_sha256=PROMPT_HASH))
    if field == "attack":
        doc["attacks"][0]["max_runtime_seconds"] += 1
    elif field == "change":
        doc["change"]["feature_intent"] = "changed"
    elif field == "impact":
        doc["impact"]["head_sha"] = "f" * 40
    elif field == "hash":
        doc["plan_hash"] = "0" * 64
    elif field == "extra":
        doc["execute"] = True
    elif field == "nested_extra":
        doc["attacks"][0]["execute"] = True
    elif field == "version":
        doc["handoff_version"] = "2.0"
    else:
        doc["attacks"][0]["max_runtime_seconds"] = "90"
    with pytest.raises(ValueError):
        load(json.dumps(doc), plan)


@pytest.mark.parametrize(
    "binding,value",
    [
        ("expected_model_id", "other-model"),
        ("expected_prompt_sha256", "b" * 64),
        ("expected_run_id", "other-run"),
        ("expected_plan_hash", "b" * 64),
    ],
)
def test_expected_binding_mismatch(plan: FrozenPlan, binding: str, value: str) -> None:
    with pytest.raises(ValueError):
        load(serialize_frozen_plan(plan, prompt_sha256=PROMPT_HASH), plan, **{binding: value})


@pytest.mark.parametrize("field", ["target_id", "fixture_id", "feature_intent"])
def test_exact_change_binding(plan: FrozenPlan, field: str) -> None:
    with pytest.raises(ValueError):
        load(
            serialize_frozen_plan(plan, prompt_sha256=PROMPT_HASH),
            plan,
            expected_change=plan.change.model_copy(update={field: "different"}),
        )


def test_empty_plan_is_reportable_but_never_executable(demo_repo: DemoRepo) -> None:
    empty = run_use_case(demo_repo, demo_repo.ui_head, {"attacks": []})[0]
    raw = serialize_frozen_plan(empty, prompt_sha256=PROMPT_HASH)
    assert json.loads(raw)["gate_status"] == "not_tested"
    restored = load(raw, empty)
    assert restored.not_tested_reason
    with pytest.raises(ValueError, match="no attacks"):
        require_executable_plan(restored)


@pytest.mark.parametrize("raw", ["{", "[]", '{"handoff_version":"1.0","handoff_version":"1.0"}'])
def test_malformed_json(plan: FrozenPlan, raw: str) -> None:
    with pytest.raises(ValueError):
        load(raw, plan)


def test_serializer_rejects_invalid_frozen_plan(plan: FrozenPlan) -> None:
    with pytest.raises(ValueError):
        serialize_frozen_plan(replace(plan, plan_hash="0" * 64), prompt_sha256=PROMPT_HASH)


def test_oversized_input_rejected_before_parse(plan: FrozenPlan) -> None:
    from gauntlet.planning.handoff import MAX_HANDOFF_BYTES

    with pytest.raises(ValueError, match="size limit"):
        load(" " * (MAX_HANDOFF_BYTES + 1), plan)


@pytest.mark.parametrize("field", ["target_id", "fixture_id"])
def test_attack_binding_rejected_even_with_recomputed_hash(plan: FrozenPlan, field: str) -> None:
    from gauntlet.planning import compute_plan_hash

    attack = plan.attacks[0].model_copy(update={field: "other"})
    mutated = replace(
        plan, attacks=(attack,), plan_hash=compute_plan_hash(plan.change, plan.impact, (attack,))
    )
    with pytest.raises(ValueError):
        serialize_frozen_plan(mutated, prompt_sha256=PROMPT_HASH)


@pytest.mark.parametrize("rejected_count", [0, 101])
def test_cli_publishes_loadable_envelope(
    rejected_count: int,
    demo_repo: DemoRepo,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    import hashlib

    from test_a01c_live_planner import (
        BedrockConverseGateway,
        RecordingClient,
        change,
        probe_p1_model_plan,
        response,
    )

    monkeypatch.setenv("RUN_LIVE_INTEGRATIONS", "1")
    monkeypatch.setattr(probe_p1_model_plan.importlib.metadata, "version", lambda _: "1.43.114")

    class Client(RecordingClient):
        def close(self) -> None:
            pass

    monkeypatch.setattr(
        probe_p1_model_plan,
        "create_bedrock_gateway",
        lambda **_: BedrockConverseGateway(
            Client(response(json.dumps({"attacks": [{}] * rejected_count}))), "test-model"
        ),
    )
    change_path = tmp_path / "change.json"
    request = change(demo_repo)
    change_path.write_text(request.model_dump_json())
    output = tmp_path / "plan.json"
    assert (
        probe_p1_model_plan.main(
            [
                "--repository",
                str(demo_repo.path),
                "--change-request",
                str(change_path),
                "--model-id",
                "test-model",
                "--region",
                "us-east-1",
                "--output",
                str(output),
                "--execute",
                "--authorize-spend",
            ]
        )
        == 0
    )
    report = json.loads(output.read_text())
    restored = load_frozen_plan(
        json.dumps(report["frozen_plan"]),
        expected_change=request,
        expected_plan_hash=report["plan_hash"],
        expected_model_id="test-model",
        expected_prompt_sha256=hashlib.sha256(
            probe_p1_model_plan.INSTRUCTIONS.read_text().encode()
        ).hexdigest(),
        expected_run_id=report["run_id"],
    )
    assert restored.attacks == ()
    assert len(restored.rejected) == rejected_count
    assert report["status"] == ("rejected" if rejected_count else "not_tested")
    assert report["gate_status"] == "not_tested"
    assert "frozen_plan" not in json.loads(capsys.readouterr().out)
