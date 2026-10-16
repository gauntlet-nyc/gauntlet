"""Pair two pinned scripted local UI reports using their stored browser evidence.

Run base and head separately with the same --run-id, then pass their report hashes
from the probe output. This diagnoses local composition only: a Cartwheel build
receipt does not establish independent server or cloud provider provenance.
"""

import argparse
import asyncio
import hashlib
import json
import re
from pathlib import Path

from gauntlet.application.gate import StaticTargetCatalog, profile_from_manifest
from gauntlet.application.gate.pair_verdict import GateAttempt, adjudicate_ui_pair
from gauntlet.contracts import (
    AttackSpec,
    ChangeRequest,
    EvidenceSubject,
    Observation,
    OracleVerdict,
)
from gauntlet.integrations.local_artifacts import LocalArtifactStore
from gauntlet.integrations.local_gate_diagnostic import freeze_diagnostic_plan
from gauntlet.ports.artifacts import StoredArtifact
from gauntlet.verification.stored_browser import StoredBrowserOracle

_MAX_REPORT_BYTES = 2_000_000


def _unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate report field")
        result[key] = value
    return result


def _read_report(path: Path, expected_sha256: str) -> dict[str, object]:
    if path.is_symlink():
        raise ValueError("report must not be a symbolic link")
    with path.open("rb") as stream:
        raw = stream.read(_MAX_REPORT_BYTES + 1)
    if len(raw) > _MAX_REPORT_BYTES or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("report size or pinned SHA-256 mismatch")
    parsed = json.loads(raw, object_pairs_hook=_unique_keys)
    if not isinstance(parsed, dict):
        raise ValueError("report must be a JSON object")
    return parsed


async def _load_attempts(
    output: Path, report: dict[str, object], attack: AttackSpec
) -> tuple[GateAttempt, ...]:
    rows = report.get("typed_attempts")
    if not isinstance(rows, list) or not rows:
        raise ValueError("typed attempts are missing")
    store = LocalArtifactStore(output / "artifacts")
    oracle = StoredBrowserOracle(
        store, primary_targets={attack.target_id: "checkout-primary-action"}
    )
    attempts: list[GateAttempt] = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "subject",
            "observation",
            "verdicts",
            "artifact_ids",
        }:
            raise ValueError("typed attempt envelope is invalid")
        subject = EvidenceSubject.model_validate_json(json.dumps(row["subject"]), strict=True)
        observation = Observation.model_validate_json(json.dumps(row["observation"]), strict=True)
        if not isinstance(row["verdicts"], list) or len(row["verdicts"]) != 1:
            raise ValueError("one typed oracle verdict is required")
        reported_verdict = OracleVerdict.model_validate_json(
            json.dumps(row["verdicts"][0]), strict=True
        )
        artifact_ids = row["artifact_ids"]
        if (
            not isinstance(artifact_ids, list)
            or artifact_ids != list(observation.evidence_ids)
            or len(set(artifact_ids)) != len(artifact_ids)
        ):
            raise ValueError("attempt artifact list differs from observation")
        step_by_artifact = {
            artifact_id: record.step_index
            for record in observation.action_log
            for artifact_id in record.evidence_ids
        }
        if set(step_by_artifact) != set(artifact_ids):
            raise ValueError("attempt artifact steps differ from observation")
        artifacts: list[StoredArtifact] = []
        for artifact_id in artifact_ids:
            item = await store.get(artifact_id)
            if item is None:
                raise ValueError("stored artifact is missing or malformed")
            binding = item.binding
            if (
                binding.evidence.artifact_id != artifact_id
                or binding.byte_size != len(item.content)
                or binding.evidence.sha256 != hashlib.sha256(item.content).hexdigest()
                or binding.subject
                != subject.model_copy(update={"step_index": step_by_artifact[artifact_id]})
            ):
                raise ValueError("stored artifact bytes or attempt binding differs")
            artifacts.append(item)
        checked_verdict = await oracle.evaluate(attack.oracle_ids[0], attack, observation, subject)
        if (
            checked_verdict.oracle_id != reported_verdict.oracle_id
            or checked_verdict.oracle_kind != reported_verdict.oracle_kind
            or checked_verdict.outcome != reported_verdict.outcome
            or checked_verdict.evidence_ids != reported_verdict.evidence_ids
        ):
            raise ValueError("reported oracle verdict differs from stored browser evidence")
        checked_verdict = checked_verdict.model_copy(
            update={"verdict_id": reported_verdict.verdict_id}
        )
        attempts.append(GateAttempt(subject, observation, (checked_verdict,), tuple(artifacts)))
    return tuple(attempts)


async def pair_reports(
    *,
    fixture_repo: Path,
    base_output: Path,
    head_output: Path,
    run_id: str,
    expected_plan_hash: str,
    base_report_sha256: str,
    head_report_sha256: str,
    clean_sha: str | None = None,
) -> dict[str, object]:
    """Recompute the scripted plan and adjudicate two hash-pinned local run records."""
    manifest = json.loads(Path("apps/cartwheel/fixture-manifest.v1.json").read_text())
    if clean_sha is not None and re.fullmatch(r"[0-9a-f]{40}", clean_sha) is None:
        raise ValueError("clean commit SHA must be full lowercase Git SHA")
    change = ChangeRequest(
        repository_id="cartwheel",
        base_sha=manifest["git_refs"]["base_sha"],
        head_sha=clean_sha or manifest["git_refs"]["head_sha"],
        fixture_id=manifest["fixture_id"],
        target_id=manifest["target_id"],
        max_cost_usd_cents=500,
        feature_intent=(
            "Clarify the product description" if clean_sha is not None else "Synthetic UI update"
        ),
    )
    frozen = (await freeze_diagnostic_plan(
            fixture_repo,
            change,
            targets=StaticTargetCatalog(profile_from_manifest(manifest)),
            run_id=run_id,
        )).frozen
    if (
        frozen.plan_hash != expected_plan_hash
        or frozen.run_id != run_id
        or len(frozen.attacks) != 1
        or frozen.rejected
    ):
        raise ValueError("trusted scripted plan identity differs from expected plan")
    if clean_sha is not None and frozen.impact.changed_files != ("src/app/products/demo/page.tsx",):
        raise ValueError("clean comparison must change only the product description page")
    attempts: dict[str, tuple[GateAttempt, ...]] = {}
    for side, output, digest, sha in (
        ("base", base_output, base_report_sha256, change.base_sha),
        (
            "clean" if clean_sha is not None else "head",
            head_output,
            head_report_sha256,
            change.head_sha,
        ),
    ):
        report = _read_report(output / "report.json", digest)
        expected_fields = {
            "mode": "scripted_local_p1_diagnostic",
            "scenario": side,
            "plan_source": "scripted_proposal_validated_against_real_diff",
            "plan_hash": frozen.plan_hash,
            "run_id": run_id,
            "plan_frozen_before_execution": True,
            "model_id": frozen.model_id,
            "change_base_sha": change.base_sha,
            "change_head_sha": change.head_sha,
            "execute_sha": sha,
            "fixture_checksum": manifest["fixture_checksum_sha256"],
            "fixture_checkout_verified": True,
            "fixture_build_receipt_verified": True,
            "server_source_verified": False,
            "attack_source_refs": [
                ref.model_dump(mode="json") for ref in frozen.attacks[0].source_refs
            ],
        }
        if any(report.get(key) != value for key, value in expected_fields.items()):
            raise ValueError(f"{side} report identity or local receipt differs from trusted plan")
        attempts["head" if side == "clean" else side] = await _load_attempts(
            output, report, frozen.attacks[0]
        )
    result = adjudicate_ui_pair(
        change=change,
        attack=frozen.attacks[0],
        run_id=run_id,
        fixture_checksum=manifest["fixture_checksum_sha256"],
        head=attempts["head"],
        base=attempts["base"],
    )
    return {
        "mode": "scripted_local_p1_paired_diagnostic",
        "plan_source": "scripted_proposal_validated_against_real_diff",
        "server_source_verified": False,
        "source_provenance": "local_cartwheel_build_receipt_only",
        "comparison": "clean_unrelated_change" if clean_sha is not None else "regression_fixture",
        "run_id": run_id,
        "plan_hash": frozen.plan_hash,
        "base_report_sha256": base_report_sha256,
        "head_report_sha256": head_report_sha256,
        "gate_status": "not_tested",
        "attribution": "unknown",
        "local_pair_status": result.verdict.status.value,
        "local_pair_attribution": result.verdict.attribution.value,
        "head_attempts": result.head_attempts,
        "head_failures": result.head_failures,
        "base_attempts": result.base_attempts,
        "base_failures": result.base_failures,
        "oracle_verdict_ids": result.oracle_verdict_ids,
        "evidence_ids": result.evidence_ids,
        "limitations": result.limitations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("fixture-repo", "base-output", "head-output", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    for name in (
        "run-id",
        "expected-plan-hash",
        "base-report-sha256",
        "head-report-sha256",
    ):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--clean-sha")
    args = parser.parse_args()
    try:
        report = asyncio.run(
            pair_reports(
                fixture_repo=args.fixture_repo,
                base_output=args.base_output,
                head_output=args.head_output,
                run_id=args.run_id,
                expected_plan_hash=args.expected_plan_hash,
                base_report_sha256=args.base_report_sha256,
                head_report_sha256=args.head_report_sha256,
                clean_sha=args.clean_sha,
            )
        )
        args.output.open("x").write(json.dumps(report, indent=2) + "\n")
    except Exception as exc:
        print(json.dumps({"gate_status": "not_tested", "error_type": type(exc).__name__}))
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
