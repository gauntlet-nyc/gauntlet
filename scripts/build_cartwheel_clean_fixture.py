"""Build an isolated product-copy sibling of the registered Cartwheel base.

The new checkout ends at clean_sha on feat/product-description. Existing
base/head commits, manifests, template checksums and snapshot registrations
are unchanged. Output includes the separate clean-template checksum and the
original registration checksum; neither is a measured false-positive rate.
Use base_sha..clean_sha as the unrelated change, with feature intent such as
"Clarify the product description". Model planning and browser verification
are separate acceptance steps; this builder does not label their outcomes.
"""

import argparse
import json
import shutil
from pathlib import Path

from build_cartwheel_fixture import FIXTURE, build, git, tree_checksum


def build_clean(destination: Path) -> dict[str, str]:
    """Generate a deterministic sibling without overwriting an existing checkout."""
    # Reserve first, including refusal of dangling symlinks, before the original
    # builder (which intentionally replaces its generated destination) runs.
    destination.mkdir(parents=True, exist_ok=False)
    registered = build(destination)
    git(destination, "checkout", "-q", "-b", "feat/product-description", registered["base_sha"])
    shutil.copytree(FIXTURE / "clean", destination, dirs_exist_ok=True)
    git(destination, "add", "-A")
    git(
        destination,
        "commit",
        "-q",
        "-m",
        "Clarify the product description",
        date="2026-10-03T12:00:00+00:00",
    )
    return {
        "base_sha": registered["base_sha"],
        "clean_sha": git(destination, "rev-parse", "HEAD"),
        "regression_head_sha": registered["head_sha"],
        "registered_fixture_checksum_sha256": registered["fixture_checksum_sha256"],
        "clean_fixture_checksum_sha256": tree_checksum(FIXTURE / "base", FIXTURE / "clean"),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, required=True, help="New generated checkout directory")
    arguments = parser.parse_args()
    print(json.dumps(build_clean(arguments.dest), indent=2))
