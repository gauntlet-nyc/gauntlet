"""Prepare local registration for operator-supplied existing Daytona snapshots.

No network requests or credential reads. This checks registration shape and
committed fixture identity, not snapshot existence, image contents, startup,
or mutable runtime order state. The image digest denotes the common runtime
image used for both revisions; it is not a claim that two source trees match.
"""

import argparse
import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path, PurePosixPath

from gauntlet.integrations.daytona.provider import RegisteredSnapshot, RegisteredTarget

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "apps/cartwheel/fixture-manifest.v1.json"
STATE = ROOT / "apps/cartwheel/fixture/base/fixture-state.json"
_SUFFIX = re.compile(r"\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}\Z")


def prepare_registration(
    *,
    base_snapshot: str,
    head_snapshot: str,
    image_digest: str,
    repo_path: str,
    preview_port: int,
    preview_domain_suffix: str,
) -> dict[str, object]:
    """Bind explicit operator infrastructure choices to the committed baseline."""
    if base_snapshot == head_snapshot or any(
        name.upper().startswith("REPLACE_") for name in (base_snapshot, head_snapshot)
    ):
        raise ValueError("two distinct actual snapshot names are required")
    path = PurePosixPath(repo_path)
    if (
        not path.is_absolute()
        or str(path) != repo_path
        or ".." in path.parts
        or repo_path == "/"
        or repo_path.startswith("//")
        or any(ord(char) < 32 or ord(char) == 127 for char in repo_path)
    ):
        raise ValueError("repository path must be an exact safe absolute POSIX path")
    if len(preview_domain_suffix) > 254 or not _SUFFIX.fullmatch(preview_domain_suffix):
        raise ValueError("preview domain suffix must be a canonical dotted DNS suffix")
    if type(preview_port) is not int:
        raise ValueError("preview port must be an integer")
    manifest = json.loads(MANIFEST.read_text())
    state = STATE.read_bytes()
    baseline = json.loads(state)
    if (
        manifest["synthetic_only"] is not True
        or baseline["synthetic_only"] is not True
        or manifest["target_id"] != "cartwheel-fixture"
        or baseline["fixture_id"] != manifest["fixture_id"]
    ):
        raise ValueError("committed synthetic fixture identity differs")
    target = RegisteredTarget(
        target_id=manifest["target_id"],
        fixture_id=manifest["fixture_id"],
        fixture_checksum=manifest["fixture_checksum_sha256"],
        fixture_state_digest=hashlib.sha256(state).hexdigest(),
        fixture_state_path=str(path / "fixture-state.json"),
        repo_path=repo_path,
        preview_port=preview_port,
        preview_domain_suffix=preview_domain_suffix,
        ready_path="/checkout",
        snapshots=(
            RegisteredSnapshot(manifest["git_refs"]["base_sha"], base_snapshot, image_digest),
            RegisteredSnapshot(manifest["git_refs"]["head_sha"], head_snapshot, image_digest),
        ),
    )
    document = asdict(target)
    document["snapshots"] = list(document["snapshots"])
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "base-snapshot",
        "head-snapshot",
        "image-digest",
        "repo-path",
        "preview-domain-suffix",
    ):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--preview-port", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        document = prepare_registration(
            base_snapshot=args.base_snapshot,
            head_snapshot=args.head_snapshot,
            image_digest=args.image_digest,
            repo_path=args.repo_path,
            preview_port=args.preview_port,
            preview_domain_suffix=args.preview_domain_suffix,
        )
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(document, indent=2) + "\n")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "environment_error", "error_type": type(exc).__name__}))
        return 1
    print(
        json.dumps(
            {
                "status": "not_tested",
                "registration_prepared": True,
                "snapshots_verified": False,
                "gate_status": "not_tested",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
