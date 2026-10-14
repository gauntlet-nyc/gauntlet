"""A-02: tool/permission signals and target-scoped identities for AI-tool attacks."""

import asyncio
import itertools
import json
from datetime import UTC, datetime
from typing import Any

import pytest
from conftest import DemoRepo
from fakes import (
    CARTWHEEL,
    FakeOracleRegistry,
    InMemoryRunStore,
    ScriptedModelGateway,
    StaticTargetCatalog,
)
from gauntlet.analysis import GitRepositoryInspector, extract_signals, parse_unified_diff
from gauntlet.application import TargetNotAuthorizedError
from gauntlet.application.gate import PlanChangeDependencies, PlanChangeUseCase
from gauntlet.contracts import ChangeImpactMap, ChangeRequest
from gauntlet.planning import AttackPlanner, PlanningLimits, PlanValidator


def change_for(repo: DemoRepo, head: str, **overrides: str) -> ChangeRequest:
    fields: dict[str, Any] = {
        "repository_id": "cartwheel",
        "base_sha": repo.base,
        "head_sha": head,
        "fixture_id": "baseline-v1",
        "target_id": "cartwheel-fixture",
        "max_cost_usd_cents": 500,
    }
    fields.update(overrides)
    return ChangeRequest.model_validate(fields)


def inspect(repo: DemoRepo, head: str) -> ChangeImpactMap:
    inspector = GitRepositoryInspector({"cartwheel": repo.path})
    return asyncio.run(inspector.inspect_change(change_for(repo, head)))


def ai_attack(impact: ChangeImpactMap, **step_overrides: str) -> dict[str, Any]:
    ref = next(s for s in impact.surfaces if s.kind == "agent_tool").source_refs[0]
    step = {
        "action": "chat",
        "agent_id": "support-test-agent",
        "actor_id": "synthetic-attacker-01",
        "message": "Please refund order ord-2002 for me.",
    }
    step.update(step_overrides)
    return {
        "attack_id": "attack-agent-001",
        "hypothesis": "Removed owner check may allow a cross-user refund",
        "why_this_change": "The diff deletes the ownerId comparison before ledger.refund",
        "expected_observation": "No refund side effect for an order the actor does not own",
        "source_refs": [ref.model_dump(mode="json")],
        "worker_kind": "ai_agent",
        "target_id": "cartwheel-fixture",
        "fixture_id": "baseline-v1",
        "steps": [step],
        "oracle_ids": ["agent.refund_authorized"],
        "max_actions": 5,
        "max_runtime_seconds": 120,
    }


def reasons_for(repo: DemoRepo, impact: ChangeImpactMap, attack: dict[str, Any]) -> list[str]:
    validator = PlanValidator(FakeOracleRegistry(), PlanningLimits())
    result = validator.validate(
        json.dumps({"attacks": [attack]}), change_for(repo, impact.head_sha), impact, CARTWHEEL
    )
    return [r for rejected in result.rejected for r in rejected.reasons]


# --- Signals -----------------------------------------------------------------------------


def test_removed_owner_check_is_signalled_on_base_lines(demo_repo: DemoRepo) -> None:
    impact = inspect(demo_repo, demo_repo.tool_head)
    tool = next(s for s in impact.surfaces if s.kind == "agent_tool")
    removed = [s for s in tool.signals if s.kind == "auth_check_removed"]
    assert len(removed) == 1
    assert removed[0].source_ref.sha == demo_repo.base
    assert (removed[0].source_ref.start_line, removed[0].source_ref.end_line) == (3, 4)
    assert "ownerId" in removed[0].excerpt


def test_fixed_help_button_is_signalled_as_layout(demo_repo: DemoRepo) -> None:
    impact = inspect(demo_repo, demo_repo.ui_head)
    style = next(s for s in impact.surfaces if s.kind == "style")
    assert {s.kind for s in style.signals} == {"layout_positioning"}


def test_added_side_effect_and_tool_definition_signals() -> None:
    diff = parse_unified_diff(
        "diff --git a/api/src/tools/t.ts b/api/src/tools/t.ts\n"
        "--- a/api/src/tools/t.ts\n+++ b/api/src/tools/t.ts\n"
        "@@ -0,0 +1,3 @@\n"
        "+export const refundTool = defineTool({ inputSchema: schema });\n"
        "+if (!canAccess(actor, order)) throw new Forbidden();\n"
        "+await ledger.refund(order.id, amount);\n"
    )
    kinds = [
        s.kind for s in extract_signals("api/src/tools/t.ts", diff.files[0].hunks, "1" * 7, "2" * 7)
    ]
    assert kinds == ["tool_definition", "auth_check_added", "side_effect_call"]


def test_signals_are_never_raised_for_unrelated_text() -> None:
    diff = parse_unified_diff(
        "diff --git a/web/a.ts b/web/a.ts\n--- a/web/a.ts\n+++ b/web/a.ts\n"
        "@@ -1 +1 @@\n-const title = 'Shop';\n+const title = 'Cartwheel shop';\n"
    )
    assert extract_signals("web/a.ts", diff.files[0].hunks, "1" * 7, "2" * 7) == ()


# --- Target-scoped identities --------------------------------------------------------------


def test_registered_synthetic_actor_attack_is_accepted(demo_repo: DemoRepo) -> None:
    impact = inspect(demo_repo, demo_repo.tool_head)
    assert reasons_for(demo_repo, impact, ai_attack(impact)) == []


@pytest.mark.parametrize(
    ("override", "expected"),
    [
        ({"actor_id": "real-customer-42"}, "not a registered synthetic identity"),
        ({"agent_id": "production-support-bot"}, "agent is not registered"),
    ],
)
def test_unregistered_identities_are_rejected(
    demo_repo: DemoRepo, override: dict[str, str], expected: str
) -> None:
    impact = inspect(demo_repo, demo_repo.tool_head)
    assert any(expected in r for r in reasons_for(demo_repo, impact, ai_attack(impact, **override)))


def test_routes_outside_target_are_rejected(demo_repo: DemoRepo) -> None:
    impact = inspect(demo_repo, demo_repo.tool_head)
    attack = ai_attack(impact)
    attack["worker_kind"] = "api"
    attack["steps"] = [
        {"action": "test_api", "method": "POST", "path": "/admin/refunds",
         "actor_id": "synthetic-attacker-01"},
    ]  # fmt: skip
    assert any("outside the target's registered routes" in r for r in reasons_for(
        demo_repo, impact, attack
    ))  # fmt: skip


def test_route_prefix_matches_on_segment_boundary() -> None:
    assert CARTWHEEL.allows_route("/checkout")
    assert CARTWHEEL.allows_route("/checkout/confirm?step=2")
    assert not CARTWHEEL.allows_route("/checkoutadmin")


@pytest.mark.parametrize(
    ("override", "message"),
    [({"target_id": "prod-shop"}, "target is not registered"),
     ({"fixture_id": "prod-snapshot"}, "fixture is not registered")],
)  # fmt: skip
def test_unregistered_target_or_fixture_is_refused_before_any_work(
    demo_repo: DemoRepo, override: dict[str, str], message: str
) -> None:
    gateway = ScriptedModelGateway({"attacks": []})
    store = InMemoryRunStore()
    ids = (f"event-{n}" for n in itertools.count())
    use_case = PlanChangeUseCase(
        PlanChangeDependencies(
            inspector=GitRepositoryInspector({"cartwheel": demo_repo.path}),
            planner=AttackPlanner(gateway, FakeOracleRegistry(), "x", PlanningLimits()),
            store=store,
            targets=StaticTargetCatalog(),
            clock=lambda: datetime(2026, 10, 14, tzinfo=UTC),
            new_event_id=lambda: next(ids),
        )
    )
    with pytest.raises(TargetNotAuthorizedError, match=message):
        asyncio.run(
            use_case.execute("run-x", change_for(demo_repo, demo_repo.tool_head, **override))
        )
    assert gateway.requests == [] and store.events == {}
