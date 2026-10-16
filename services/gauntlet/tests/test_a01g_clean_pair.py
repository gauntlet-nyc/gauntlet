"""The unrelated product-copy sibling is measured through the same stored UI oracle."""

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest
from test_a01f_paired_gate import RUN_ID, load, make_attempt, write_report

from gauntlet.contracts import ChangeRequest
from gauntlet.integrations.local_gate_diagnostic import freeze_diagnostic_plan

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def clean_pair_input(tmp_path: Path) -> dict[str, object]:
    repo = tmp_path / "fixture"
    builder = subprocess.run(
        [sys.executable, "scripts/build_cartwheel_clean_fixture.py", "--dest", str(repo)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    built = json.loads(builder.stdout)
    manifest = json.loads((ROOT / "apps/cartwheel/fixture-manifest.v1.json").read_text())
    assert built["base_sha"] == manifest["git_refs"]["base_sha"]
    assert built["registered_fixture_checksum_sha256"] == manifest["fixture_checksum_sha256"]
    change = ChangeRequest(
        repository_id="cartwheel",
        base_sha=built["base_sha"],
        head_sha=built["clean_sha"],
        fixture_id=manifest["fixture_id"],
        target_id=manifest["target_id"],
        max_cost_usd_cents=500,
        feature_intent="Clarify the product description",
    )
    frozen = asyncio.run(freeze_diagnostic_plan(repo, change, run_id=RUN_ID)).frozen
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", change.base_sha], check=True)
    base_frozen = asyncio.run(freeze_diagnostic_plan(repo, change, run_id=RUN_ID)).frozen
    assert base_frozen.plan_hash == frozen.plan_hash
    assert base_frozen.attacks == frozen.attacks
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", change.head_sha], check=True)
    assert frozen.impact.changed_files == ("src/app/products/demo/page.tsx",)
    assert len(frozen.attacks) == 1
    outputs = {side: tmp_path / side for side in ("base", "clean")}
    digests: dict[str, str] = {}
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
            "execute_sha": change.base_sha if side == "base" else change.head_sha,
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
        "fixture_repo": repo,
        "base_output": outputs["base"],
        "head_output": outputs["clean"],
        "run_id": RUN_ID,
        "expected_plan_hash": frozen.plan_hash,
        "base_report_sha256": digests["base"],
        "head_report_sha256": digests["clean"],
        "clean_sha": built["clean_sha"],
    }


def test_clean_pair_passes_without_product_gate_claim(clean_pair_input: dict[str, object]) -> None:
    result = asyncio.run(load("probe_p1_paired_gate").pair_reports(**clean_pair_input))
    assert result["comparison"] == "clean_unrelated_change"
    assert result["gate_status"] == "not_tested"
    assert result["attribution"] == "unknown"
    assert result["local_pair_status"] == "passed"
    assert result["head_attempts"] == result["base_attempts"] == 2
    assert result["head_failures"] == result["base_failures"] == 0
    assert result["server_source_verified"] is False


def test_clean_pair_rejects_wrong_report_scenario_even_with_new_digest(
    clean_pair_input: dict[str, object],
) -> None:
    output = clean_pair_input["head_output"]
    report = json.loads((output / "report.json").read_text())
    report["scenario"] = "head"
    clean_pair_input["head_report_sha256"] = write_report(output, report)
    with pytest.raises(ValueError, match="identity or local receipt"):
        asyncio.run(load("probe_p1_paired_gate").pair_reports(**clean_pair_input))


def test_clean_pair_rejects_regression_sha(clean_pair_input: dict[str, object]) -> None:
    manifest = json.loads((ROOT / "apps/cartwheel/fixture-manifest.v1.json").read_text())
    clean_pair_input["clean_sha"] = manifest["git_refs"]["head_sha"]
    with pytest.raises(ValueError, match="trusted scripted plan identity|product description"):
        asyncio.run(load("probe_p1_paired_gate").pair_reports(**clean_pair_input))
