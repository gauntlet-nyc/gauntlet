"""Target onboarding status: what is registered and what an operator still has to configure.

Read-only. Targets come only from committed synthetic manifests, never from a request body.
"""

import json
from importlib import resources
from typing import Any

from fastapi import APIRouter

from gauntlet.settings import Settings

from ..container import get_container
from ..schemas import (
    OnboardingStep,
    OnboardingTarget,
    OnboardingView,
    TargetIdentity,
    TargetRoute,
)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


def _target(manifest: dict[str, Any], base_sha: str, head_sha: str) -> OnboardingTarget:
    return OnboardingTarget(
        target_id=manifest["target_id"],
        fixture_id=manifest["fixture_id"],
        synthetic_only=manifest.get("synthetic_only") is True,
        base_sha=base_sha,
        head_sha=head_sha,
        fixture_checksum_sha256=manifest["fixture_checksum_sha256"],
        routes=[
            TargetRoute(path=r["path"], primary_action=r.get("primary_action"))
            for r in manifest.get("routes", [])
        ],
        identities=[
            TargetIdentity(id=i["id"], role=i["role"]) for i in manifest.get("identities", [])
        ],
        github_repository=None,
    )


@router.get("")
async def onboarding_status() -> OnboardingView:
    container = get_container()
    settings = container.settings
    core = Settings.from_env()
    main = json.loads(
        resources.files("gauntlet.api")
        .joinpath("fixtures", "cartwheel-fixture-manifest.v1.json")
        .read_text()
    )
    refund = json.loads(settings.refund_manifest.read_text())
    targets = [
        _target(main, main["git_refs"]["base_sha"], main["git_refs"]["head_sha"]),
        _target(refund, refund["change"]["base_sha"], refund["change"]["head_sha"]),
    ]
    allowed = {
        t.strip() for t in (core.optional("GAUNTLET_ALLOWED_TARGET_IDS") or "").split(",") if t
    }
    github_missing = settings.missing_env("github_app")
    steps = [
        OnboardingStep(
            step="Register a synthetic target manifest",
            done=all(t.synthetic_only for t in targets),
            detail="apps/cartwheel/*manifest.v1.json; only synthetic_only targets are accepted",
        ),
        OnboardingStep(
            step="Build deterministic base/head fixture commits and pin the checksum",
            done=all(t.base_sha and t.head_sha for t in targets),
            detail="scripts/build_cartwheel_fixture.py and build_cartwheel_refund_fixture.py",
        ),
        OnboardingStep(
            step="Allow the target for live runs",
            done=main["target_id"] in allowed,
            detail="set GAUNTLET_ALLOWED_TARGET_IDS=" + main["target_id"],
        ),
        OnboardingStep(
            step="Register base/head sandbox snapshots",
            done=core.optional("GAUNTLET_DAYTONA_REGISTRATION") is not None,
            detail="scripts/prepare_cartwheel_registration.py, then GAUNTLET_DAYTONA_REGISTRATION",
        ),
        OnboardingStep(
            step="Install the GitHub App and bind the repository",
            done=not github_missing,
            detail="missing: " + ", ".join(github_missing) if github_missing else "configured",
        ),
        OnboardingStep(
            step="Configure reviewer tokens",
            done=settings.has_reviewers,
            detail="GAUNTLET_REVIEWER_TOKENS=name:token (dev-grade)",
        ),
    ]
    return OnboardingView(targets=targets, steps=steps)
