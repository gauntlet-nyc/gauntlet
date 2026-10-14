"""Build the Cartwheel fixture repo with deterministic base and per-change head commits.

base = apps/cartwheel/fixture/base. Each entry in fixture/changes.json becomes a branch off base
with apps/cartwheel/fixture/changes/<id> overlaid. Fixed author, dates and config make the SHAs
reproducible for the same templates and git version. With --write-manifest the SHAs and checksum
are recorded in fixture-manifest.v1.json.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "apps/cartwheel/fixture"
MANIFEST = ROOT / "apps/cartwheel/fixture-manifest.v1.json"
ENV = {
    "GIT_AUTHOR_NAME": "Cartwheel Fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "Cartwheel Fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}


def load_changes() -> list[dict[str, str]]:
    changes: list[dict[str, str]] = json.loads((FIXTURE / "changes.json").read_text())
    return changes


def tree_checksum() -> str:
    """sha256 over relative paths and contents of every template dir plus changes.json."""
    digest = hashlib.sha256()
    dirs = [FIXTURE / "base", *(FIXTURE / "changes" / c["id"] for c in load_changes())]
    for base in dirs:
        for path in sorted(p for p in base.rglob("*") if p.is_file()):
            digest.update(f"{base.name}/{path.relative_to(base).as_posix()}\0".encode())
            digest.update(path.read_bytes())
    digest.update((FIXTURE / "changes.json").read_bytes())
    return digest.hexdigest()


def git(repo: Path, *args: str, date: str | None = None) -> str:
    env = {**os.environ, **ENV}
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    out = subprocess.run(
        ["git", *args], cwd=repo, env=env, check=True, capture_output=True, text=True
    )
    return out.stdout.strip()


def build(dest: Path) -> dict[str, Any]:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(FIXTURE / "base", dest)
    git(dest, "init", "-q", "-b", "main")
    git(dest, "add", "-A")
    git(
        dest, "commit", "-q", "-m", "Initial Cartwheel storefront", date="2026-10-01T12:00:00+00:00"
    )
    base_sha = git(dest, "rev-parse", "HEAD")
    heads: dict[str, str] = {}
    for change in load_changes():
        git(dest, "checkout", "-q", "-b", change["branch"], base_sha)
        shutil.copytree(FIXTURE / "changes" / change["id"], dest, dirs_exist_ok=True)
        git(dest, "add", "-A")
        git(dest, "commit", "-q", "-m", change["message"], date=change["date"])
        heads[change["id"]] = git(dest, "rev-parse", "HEAD")
    git(dest, "checkout", "-q", "main")
    return {"base_sha": base_sha, "heads": heads, "fixture_checksum_sha256": tree_checksum()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dest", type=Path, default=ROOT / "artifacts/cartwheel-fixture")
    parser.add_argument("--write-manifest", action="store_true")
    args = parser.parse_args()
    result = build(args.dest)
    print(json.dumps(result, indent=2))
    if args.write_manifest:
        manifest = json.loads(MANIFEST.read_text())
        manifest.pop("git_refs", None)
        manifest["base_sha"] = result["base_sha"]
        manifest["changes"] = [
            {
                "id": c["id"],
                "branch": c["branch"],
                "head_sha": result["heads"][c["id"]],
                "feature_intent": c["feature_intent"],
            }
            for c in load_changes()
        ]
        manifest["fixture_checksum_sha256"] = result["fixture_checksum_sha256"]
        manifest["status"] = "commits built from templates; not yet run in a sandbox"
        MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
        sys.stderr.write(f"updated {MANIFEST}\n")
