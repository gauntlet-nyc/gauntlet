"""The benign product-copy sibling preserves the registered regression fixture."""

import asyncio
import json
import subprocess
import sys
from pathlib import Path

from gauntlet.analysis import GitRepositoryInspector
from gauntlet.contracts import ChangeRequest
from gauntlet.planning.worker_selector import allowed_workers

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/build_cartwheel_clean_fixture.py"
MANIFEST = ROOT / "apps/cartwheel/fixture-manifest.v1.json"


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


def test_clean_sibling_is_reproducible_and_preserves_registered_revisions(tmp_path: Path) -> None:
    original_manifest = MANIFEST.read_bytes()
    first_repo, second_repo = tmp_path / "first", tmp_path / "second"
    first, second = build(first_repo), build(second_repo)
    manifest = json.loads(original_manifest)
    assert first == second
    assert first["base_sha"] == manifest["git_refs"]["base_sha"]
    assert first["regression_head_sha"] == manifest["git_refs"]["head_sha"]
    assert first["registered_fixture_checksum_sha256"] == manifest["fixture_checksum_sha256"]
    assert first["clean_sha"] not in {first["base_sha"], first["regression_head_sha"]}
    assert git(first_repo, "rev-parse", "HEAD^") == first["base_sha"]
    assert git(first_repo, "status", "--porcelain") == ""
    assert MANIFEST.read_bytes() == original_manifest
    assert git(first_repo, "diff", "--name-only", first["base_sha"], first["clean_sha"]) == (
        "src/app/products/demo/page.tsx"
    )
    before = git(first_repo, "show", first["base_sha"] + ":src/app/products/demo/page.tsx")
    after = git(first_repo, "show", first["clean_sha"] + ":src/app/products/demo/page.tsx")
    assert after == before.replace("A synthetic product.", "A synthetic wheel.")
    assert git(first_repo, "rev-parse", first["clean_sha"] + ":src/app/checkout") == git(
        first_repo, "rev-parse", first["base_sha"] + ":src/app/checkout"
    )


def test_real_inspector_exposes_product_surface_without_checkout_diff(tmp_path: Path) -> None:
    repository = tmp_path / "fixture"
    refs = build(repository)
    manifest = json.loads(MANIFEST.read_text())
    change = ChangeRequest(
        repository_id="cartwheel",
        base_sha=refs["base_sha"],
        head_sha=refs["clean_sha"],
        fixture_id=manifest["fixture_id"],
        target_id=manifest["target_id"],
        max_cost_usd_cents=500,
        feature_intent="Clarify the product description",
    )
    impact = asyncio.run(GitRepositoryInspector({"cartwheel": repository}).inspect_change(change))
    assert impact.changed_files == ("src/app/products/demo/page.tsx",)
    assert "ui" in allowed_workers(impact)


def test_existing_destination_is_preserved(tmp_path: Path) -> None:
    destination = tmp_path / "occupied"
    destination.mkdir()
    sentinel = destination / "keep.txt"
    sentinel.write_text("keep")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--dest", str(destination)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert sentinel.read_text() == "keep"
