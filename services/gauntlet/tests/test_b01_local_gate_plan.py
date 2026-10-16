"""B-01 local diagnostic freezes a diff-cited plan before browser execution."""

import asyncio

from conftest import DemoRepo

from gauntlet.contracts import ChangeRequest
from gauntlet.integrations.local_gate_diagnostic import freeze_diagnostic_plan


def change(repo: DemoRepo, head: str) -> ChangeRequest:
    return ChangeRequest(
        repository_id="cartwheel",
        base_sha=repo.base,
        head_sha=head,
        fixture_id="baseline-v1",
        target_id="cartwheel-fixture",
        max_cost_usd_cents=500,
        feature_intent="Synthetic UI change",
    )


def test_real_diff_is_cited_and_plan_event_precedes_execution(demo_repo: DemoRepo) -> None:
    result = asyncio.run(
        freeze_diagnostic_plan(demo_repo.path, change(demo_repo, demo_repo.ui_head))
    )
    assert len(result.frozen.attacks) == 1
    attack = result.frozen.attacks[0]
    assert attack.worker_kind == "ui"
    assert attack.source_refs[0] in tuple(
        ref for surface in result.frozen.impact.surfaces for ref in surface.source_refs
    )
    assert [event.event_type for event in result.events] == ["impact_mapped", "plan_frozen"]
    assert result.events[-1].payload["plan_hash"] == result.frozen.plan_hash
    assert result.model_calls == 1


def test_no_changed_surface_freezes_not_tested_without_model_call(demo_repo: DemoRepo) -> None:
    result = asyncio.run(freeze_diagnostic_plan(demo_repo.path, change(demo_repo, demo_repo.base)))
    assert result.frozen.attacks == ()
    assert result.frozen.not_tested_reason == "no testable surface in the change"
    assert result.events[-1].event_type == "plan_frozen"
    assert result.model_calls == 0
