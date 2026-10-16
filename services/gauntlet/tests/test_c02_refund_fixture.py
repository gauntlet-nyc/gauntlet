"""Refund-tool sibling (ported from PR #11) leaves the registered Help-button fixture unchanged."""

import asyncio
import json
import subprocess
import sys
from pathlib import Path

from gauntlet.analysis import GitRepositoryInspector
from gauntlet.contracts import ChangeRequest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/build_cartwheel_refund_fixture.py"
MANIFEST = ROOT / "apps/cartwheel/fixture-manifest.v1.json"
REFUND_MANIFEST = ROOT / "apps/cartwheel/refund-fixture-manifest.v1.json"
TOOL = "api/src/tools/request_refund.ts"


def build(destination: Path) -> dict[str, str]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--dest", str(destination)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments], cwd=repository, capture_output=True, text=True, check=True
    ).stdout.strip()


def test_refund_sibling_is_reproducible_and_matches_its_manifest(tmp_path: Path) -> None:
    registered_bytes = MANIFEST.read_bytes()
    first, second = build(tmp_path / "a"), build(tmp_path / "b")
    assert first == second
    registered = json.loads(registered_bytes)
    assert first["registered_base_sha"] == registered["git_refs"]["base_sha"]
    assert first["registered_head_sha"] == registered["git_refs"]["head_sha"]
    assert first["registered_fixture_checksum_sha256"] == registered["fixture_checksum_sha256"]
    assert MANIFEST.read_bytes() == registered_bytes
    refund = json.loads(REFUND_MANIFEST.read_text())
    assert refund["change"]["base_sha"] == first["refund_base_sha"]
    assert refund["change"]["head_sha"] == first["refund_head_sha"]
    assert refund["change"]["parent_registered_base_sha"] == first["registered_base_sha"]
    assert refund["fixture_checksum_sha256"] == first["refund_fixture_checksum_sha256"]
    repo = tmp_path / "a"
    assert git(repo, "rev-parse", "HEAD^") == first["refund_base_sha"]
    assert git(repo, "rev-parse", first["refund_base_sha"] + "^") == first["registered_base_sha"]
    assert git(repo, "status", "--porcelain") == ""
    changed = git(repo, "diff", "--name-only", first["refund_base_sha"], first["refund_head_sha"])
    assert changed == TOOL
    before = git(repo, "show", f"{first['refund_base_sha']}:{TOOL}")
    after = git(repo, "show", f"{first['refund_head_sha']}:{TOOL}")
    assert "order.ownerId !== ctx.actorId" in before
    assert "order.ownerId !== ctx.actorId" not in after


def test_real_inspector_flags_removed_ownership_check(tmp_path: Path) -> None:
    repository = tmp_path / "fixture"
    refs = build(repository)
    refund = json.loads(REFUND_MANIFEST.read_text())
    change = ChangeRequest(
        repository_id="cartwheel",
        base_sha=refs["refund_base_sha"],
        head_sha=refs["refund_head_sha"],
        fixture_id=refund["fixture_id"],
        target_id=refund["target_id"],
        max_cost_usd_cents=500,
        feature_intent=refund["change"]["feature_intent"],
    )
    impact = asyncio.run(GitRepositoryInspector({"cartwheel": repository}).inspect_change(change))
    assert impact.changed_files == (TOOL,)
    signals = {s.kind for surface in impact.surfaces for s in surface.signals}
    assert "auth_check_removed" in signals
