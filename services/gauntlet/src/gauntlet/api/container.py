"""Composition root for the demo API: one process-wide set of services."""

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from importlib import resources

from gauntlet.application.gate import ApprovalService
from gauntlet.ports import ReplayWorld

from .offline.history import FixtureHistory
from .services.gate import GateService
from .services.recall import RecallService
from .settings import REPO_ROOT, ApiSettings, get_settings
from .stores import InMemoryApprovalStore


def _manifests(settings: ApiSettings) -> dict[str, dict[str, str]]:
    main = json.loads(
        resources.files("gauntlet.api")
        .joinpath("fixtures", "cartwheel-fixture-manifest.v1.json")
        .read_text()
    )
    refund = json.loads(settings.refund_manifest.read_text())
    base = {"target_id": main["target_id"], "fixture_id": main["fixture_id"]}
    return {
        "help-button": {
            **base,
            "base_sha": main["git_refs"]["base_sha"],
            "head_sha": main["git_refs"]["head_sha"],
        },
        "refund-tool": {
            "target_id": refund["target_id"],
            "fixture_id": refund["fixture_id"],
            "base_sha": refund["change"]["base_sha"],
            "head_sha": refund["change"]["head_sha"],
        },
        # Clean sibling SHA is recorded in docs/RUNBOOK.md and test_c01f_clean_fixture.py.
        "clean": {
            **base,
            "base_sha": main["git_refs"]["base_sha"],
            "head_sha": "27548050633077b5d865431fd736fb9b92a28085",
        },
    }


@dataclass
class Container:
    settings: ApiSettings
    gate: GateService
    recall: RecallService
    approval_store: InMemoryApprovalStore
    approvals: ApprovalService
    # review item_id -> (approval_id, plan_sha256, decision)
    review_decisions: dict[str, tuple[str, str, str]] = field(default_factory=dict)


def build_container(settings: ApiSettings) -> Container:
    refund = json.loads(settings.refund_manifest.read_text())
    world = ReplayWorld(
        source_sha=refund["change"]["head_sha"],
        fixture_id=refund["fixture_id"],
        fixture_checksum=refund["fixture_checksum_sha256"],
    )
    store = InMemoryApprovalStore()
    return Container(
        settings=settings,
        gate=GateService(settings, _manifests(settings)),
        recall=RecallService(FixtureHistory.load(settings.history_dir), world),
        approval_store=store,
        approvals=ApprovalService(
            store,
            clock=lambda: datetime.now(UTC),
            new_approval_id=lambda: f"appr-{uuid.uuid4().hex[:12]}",
        ),
    )


@lru_cache(maxsize=1)
def get_container() -> Container:
    return build_container(get_settings())


__all__ = ["REPO_ROOT", "Container", "build_container", "get_container"]
