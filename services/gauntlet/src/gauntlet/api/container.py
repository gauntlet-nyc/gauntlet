"""Composition root for the demo API: one process-wide set of services."""

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from importlib import resources

from gauntlet.application.gate import ApprovalService
from gauntlet.composition import build_memory, build_recall
from gauntlet.settings import Settings

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


def _gate_service(settings: ApiSettings, core: Settings) -> GateService:
    service = GateService(settings, _manifests(settings))
    if core.run_live_integrations and settings.provider_configured("surrealdb_agent_memory"):
        service.memory, service.memory_label = build_memory("surreal", core)
    return service


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
    core = Settings.from_env()
    model = core.model_provider
    if model != "scripted" and (not core.run_live_integrations or GateService.missing(core, model)):
        model = "scripted"
    store = InMemoryApprovalStore()
    return Container(
        settings=settings,
        gate=_gate_service(settings, core),
        recall=RecallService(build_recall(core, model=model, history_dir=settings.history_dir)),
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
