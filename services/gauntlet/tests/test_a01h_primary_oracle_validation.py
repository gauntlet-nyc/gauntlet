"""Planner candidates must be executable by the registered hard UI oracle."""

import asyncio
import json

import pytest
from conftest import DemoRepo
from fakes import ScriptedModelGateway

from gauntlet.analysis import GitRepositoryInspector
from gauntlet.application.gate import profile_from_manifest
from gauntlet.contracts import ChangeRequest
from gauntlet.planning import AttackPlanner, PlanningLimits
from gauntlet.verification.catalog import OracleCatalog
from gauntlet.verification.registry import RegisteredOracleRegistry


def _validate(demo_repo: DemoRepo, steps: list[dict[str, object]]) -> tuple[int, tuple[str, ...]]:
    change = ChangeRequest(
        repository_id="cartwheel",
        base_sha=demo_repo.base,
        head_sha=demo_repo.ui_head,
        fixture_id="baseline-v1",
        target_id="cartwheel-fixture",
        max_cost_usd_cents=50,
    )
    impact = asyncio.run(
        GitRepositoryInspector({"cartwheel": demo_repo.path}).inspect_change(change)
    )
    ref = next(surface for surface in impact.surfaces if surface.kind == "style").source_refs[0]
    attack = {
        "attack_id": "live-shaped-proposal",
        "hypothesis": "A fixed Help button may obscure the primary action",
        "why_this_change": "The cited CSS adds fixed positioning",
        "expected_observation": "Checkout action receives a click",
        "source_refs": [ref.model_dump(mode="json")],
        "worker_kind": "ui",
        "target_id": "cartwheel-fixture",
        "fixture_id": "baseline-v1",
        "steps": steps,
        "oracle_ids": ["ui.primary_action_reachable"],
        "max_actions": 10,
        "max_runtime_seconds": 90,
    }
    registry = RegisteredOracleRegistry(
        plans=(),
        primary_targets={"cartwheel-fixture": "checkout-primary-action"},
        primary_routes={"cartwheel-fixture": "/checkout"},
        evidence=(),
    )
    catalog = OracleCatalog([registry])
    profile = profile_from_manifest(
        {
            "target_id": "cartwheel-fixture",
            "fixture_id": "baseline-v1",
            "synthetic_only": True,
            "routes": [{"path": "/checkout"}, {"path": "/products/demo"}],
            "identities": [],
        }
    )
    draft = asyncio.run(
        AttackPlanner(
            ScriptedModelGateway(json.dumps({"attacks": [attack]})),
            catalog,
            "trusted planner instructions",
            PlanningLimits(),
        ).plan(change, impact, (), profile)
    )
    result = draft.validation
    return len(result.accepted), tuple(reason for r in result.rejected for reason in r.reasons)


@pytest.mark.parametrize(
    "steps",
    [
        [
            {"action": "navigate", "path": "/products/demo"},
            {"action": "resize", "width": 899, "height": 800},
            {"action": "click", "target": "help-button"},
        ],
        [
            {"action": "navigate", "path": "/checkout"},
            {"action": "inspect", "target": "checkout-primary-action"},
            {"action": "click", "target": "help-button"},
        ],
        [
            {"action": "navigate", "path": "/checkout"},
            {"action": "click", "target": "checkout-primary-action"},
        ],
    ],
)
def test_primary_oracle_rejects_steps_that_cannot_supply_click_evidence(
    demo_repo: DemoRepo, steps: list[dict[str, object]]
) -> None:
    accepted, reasons = _validate(demo_repo, steps)
    assert accepted == 0
    assert any("primary action" in reason for reason in reasons)


def test_primary_oracle_accepts_checkout_after_other_route_with_evidence(
    demo_repo: DemoRepo,
) -> None:
    accepted, reasons = _validate(
        demo_repo,
        [
            {"action": "navigate", "path": "/products/demo"},
            {"action": "navigate", "path": "/checkout"},
            {"action": "resize", "width": 375, "height": 812},
            {"action": "inspect", "target": "checkout-primary-action"},
            {"action": "click", "target": "checkout-primary-action"},
            {"action": "capture", "label": "after-click"},
        ],
    )
    assert accepted == 1
    assert reasons == ()
