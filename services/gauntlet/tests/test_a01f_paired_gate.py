"""A-01f reloads two local runs and rechecks stored browser proof before pairing."""

import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest
from fakes import StaticTargetCatalog

from gauntlet.contracts import ActionRecord, ChangeRequest, EvidenceSubject, Observation
from gauntlet.integrations.local_artifacts import LocalArtifactStore
from gauntlet.integrations.local_gate_diagnostic import freeze_diagnostic_plan
from gauntlet.verification.stored_browser import StoredBrowserOracle

ROOT = Path(__file__).resolve().parents[3]
RUN_ID = "run-local-pair"
TARGET = "checkout-primary-action"
PNG = b"\x89PNG\r\n\x1a\nsynthetic"


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def make_attempt(output: Path, frozen: object, side: str, index: int) -> dict[str, object]:
    attack = frozen.attacks[0]
    change = frozen.change
    sha = change.head_sha if side in {"head", "clean"} else change.base_sha
    checksum = json.loads((ROOT / "apps/cartwheel/fixture-manifest.v1.json").read_text())[
        "fixture_checksum_sha256"
    ]
    subject = EvidenceSubject(
        run_id=RUN_ID,
        attempt_id=f"attempt-{side}-{index}",
        observation_id=f"observation-{side}-{index}",
        environment_id=f"environment-{side}-{index}",
        source_sha=sha,
        fixture_checksum=checksum,
        collector="browser_collector",
    )
    store = LocalArtifactStore(output / "artifacts")
    hit = "help-button" if side == "head" else TARGET
    geometry = {
        "target": TARGET,
        "rect": {"x": 20, "y": 700, "width": 140, "height": 44},
        "viewport": {"width": 375, "height": 812},
        "hit_target": hit,
    }
    inspect = await store.put(
        json.dumps(geometry).encode(),
        "application/json",
        subject.model_copy(update={"step_index": 2}),
    )
    click = await store.put(
        json.dumps({**geometry, "received_target": hit, "trusted": True}).encode(),
        "application/json",
        subject.model_copy(update={"step_index": 3}),
    )
    click_image = await store.put(PNG, "image/png", subject.model_copy(update={"step_index": 3}))
    capture = await store.put(PNG, "image/png", subject.model_copy(update={"step_index": 4}))
    ids = tuple(binding.evidence.artifact_id for binding in (inspect, click, click_image, capture))
    records = tuple(
        ActionRecord(
            step_index=i,
            action=step.action,
            outcome="blocked" if i == 3 and side == "head" else "ok",
            evidence_ids={2: (ids[0],), 3: ids[1:3], 4: (ids[3],)}.get(i, ()),
        )
        for i, step in enumerate(attack.steps)
    )
    observation = Observation(
        observation_id=subject.observation_id,
        attack_id=attack.attack_id,
        environment_id=subject.environment_id,
        source_sha=sha,
        fixture_checksum=checksum,
        status="completed",
        action_log=records,
        evidence_ids=ids,
    )
    oracle = StoredBrowserOracle(store, primary_targets={change.target_id: TARGET})
    verdict = await oracle.evaluate(attack.oracle_ids[0], attack, observation, subject)
    assert verdict.outcome.value == ("fail" if side == "head" else "pass")
    return {
        "subject": subject.model_dump(mode="json"),
        "observation": observation.model_dump(mode="json"),
        "verdicts": [verdict.model_dump(mode="json")],
        "artifact_ids": list(ids),
    }


def write_report(output: Path, report: dict[str, object]) -> str:
    raw = (json.dumps(report, indent=2) + "\n").encode()
    (output / "report.json").write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def pair_input(tmp_path: Path) -> dict[str, object]:
    builder = load("build_cartwheel_fixture")
    fixture_repo = tmp_path / "fixture"
    built = builder.build(fixture_repo)
    manifest = json.loads((ROOT / "apps/cartwheel/fixture-manifest.v1.json").read_text())
    assert built["base_sha"] == manifest["git_refs"]["base_sha"]
    assert built["head_sha"] == manifest["git_refs"]["head_sha"]
    change = ChangeRequest(
        repository_id="cartwheel",
        base_sha=built["base_sha"],
        head_sha=built["head_sha"],
        fixture_id=manifest["fixture_id"],
        target_id=manifest["target_id"],
        max_cost_usd_cents=500,
        feature_intent="Synthetic UI update",
    )
    frozen = asyncio.run(
        freeze_diagnostic_plan(fixture_repo, change, targets=StaticTargetCatalog(), run_id=RUN_ID)
    ).frozen
    outputs = {side: tmp_path / side for side in ("base", "head")}
    digests = {}
    for side, output in outputs.items():
        output.mkdir()
        attempts = [asyncio.run(make_attempt(output, frozen, side, i)) for i in (1, 2)]
        report = {
            "mode": "scripted_local_p1_diagnostic",
            "scenario": side,
            "plan_source": "scripted_proposal_validated_against_real_diff",
            "plan_hash": frozen.plan_hash,
            "run_id": RUN_ID,
            "plan_frozen_before_execution": True,
            "model_id": frozen.model_id,
            "change_base_sha": change.base_sha,
            "change_head_sha": change.head_sha,
            "execute_sha": change.head_sha if side == "head" else change.base_sha,
            "fixture_checksum": manifest["fixture_checksum_sha256"],
            "fixture_checkout_verified": True,
            "fixture_build_receipt_verified": True,
            "server_source_verified": False,
            "attack_source_refs": [
                ref.model_dump(mode="json") for ref in frozen.attacks[0].source_refs
            ],
            "typed_attempts": attempts,
        }
        digests[side] = write_report(output, report)
    return {
        "fixture_repo": fixture_repo,
        "base_output": outputs["base"],
        "head_output": outputs["head"],
        "run_id": RUN_ID,
        "expected_plan_hash": frozen.plan_hash,
        "base_report_sha256": digests["base"],
        "head_report_sha256": digests["head"],
    }


def pair(data: dict[str, object]) -> dict[str, object]:
    return asyncio.run(load("probe_p1_paired_gate").pair_reports(**data))


def test_base_and_head_checkouts_freeze_same_scripted_plan(tmp_path: Path) -> None:
    builder = load("build_cartwheel_fixture")
    repo = tmp_path / "fixture"
    built = builder.build(repo)
    change = ChangeRequest(
        repository_id="cartwheel",
        base_sha=built["base_sha"],
        head_sha=built["head_sha"],
        fixture_id="baseline-v1",
        target_id="cartwheel-fixture",
        max_cost_usd_cents=500,
        feature_intent="Synthetic UI update",
    )
    builder.git(repo, "checkout", "-q", built["base_sha"])
    base = asyncio.run(
        freeze_diagnostic_plan(repo, change, targets=StaticTargetCatalog(), run_id=RUN_ID)
    ).frozen
    builder.git(repo, "checkout", "-q", built["head_sha"])
    head = asyncio.run(
        freeze_diagnostic_plan(repo, change, targets=StaticTargetCatalog(), run_id=RUN_ID)
    ).frozen
    assert base.run_id == head.run_id == RUN_ID
    assert base.plan_hash == head.plan_hash
    assert base.attacks == head.attacks


def test_paired_stored_artifacts_produce_labeled_local_verdict(
    pair_input: dict[str, object],
) -> None:
    result = pair(pair_input)
    assert result["gate_status"] == "not_tested"
    assert result["attribution"] == "unknown"
    assert result["local_pair_status"] == "confirmed_regression"
    assert result["local_pair_attribution"] == "introduced"
    assert result["head_attempts"] == result["head_failures"] == 2
    assert result["base_attempts"] == 2 and result["base_failures"] == 0
    assert result["mode"] == "scripted_local_p1_paired_diagnostic"
    assert result["server_source_verified"] is False
    assert result["source_provenance"] == "local_cartwheel_build_receipt_only"


def test_report_tamper_rejected_by_independent_digest(pair_input: dict[str, object]) -> None:
    path = pair_input["head_output"] / "report.json"
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="pinned SHA-256"):
        pair(pair_input)


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_id", "other-run"),
        ("fixture_checksum", "0" * 64),
        ("fixture_build_receipt_verified", False),
        ("execute_sha", "0" * 40),
        ("plan_hash", "0" * 64),
    ],
)
def test_mismatched_identity_or_receipt_rejected_even_when_digest_replaced(
    pair_input: dict[str, object], field: str, value: object
) -> None:
    output = pair_input["head_output"]
    report = json.loads((output / "report.json").read_text())
    report[field] = value
    pair_input["head_report_sha256"] = write_report(output, report)
    with pytest.raises(ValueError, match="identity or local receipt"):
        pair(pair_input)


@pytest.mark.parametrize("damage", ["missing", "corrupt"])
def test_missing_or_corrupt_artifact_rejected(pair_input: dict[str, object], damage: str) -> None:
    output = pair_input["head_output"]
    artifact = next((output / "artifacts").glob("*.artifact"))
    if damage == "missing":
        artifact.unlink()
    else:
        artifact.write_bytes(artifact.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="stored artifact"):
        pair(pair_input)


def test_missing_attempt_cannot_confirm(pair_input: dict[str, object]) -> None:
    output = pair_input["head_output"]
    report = json.loads((output / "report.json").read_text())
    report["typed_attempts"].pop()
    pair_input["head_report_sha256"] = write_report(output, report)
    result = pair(pair_input)
    assert result["gate_status"] == "not_tested"
    assert result["local_pair_status"] == "suspected"


def test_forged_oracle_outcome_rejected_by_recomputed_oracle(pair_input: dict[str, object]) -> None:
    output = pair_input["head_output"]
    report = json.loads((output / "report.json").read_text())
    report["typed_attempts"][0]["verdicts"][0]["outcome"] = "pass"
    pair_input["head_report_sha256"] = write_report(output, report)
    with pytest.raises(ValueError, match="reported oracle verdict"):
        pair(pair_input)
