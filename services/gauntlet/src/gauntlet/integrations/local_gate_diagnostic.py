"""Credential-free P1 diagnostic using A's real diff, validator and plan freeze.

The proposal is scripted and fixed to a narrow Checkout click probe. This
checks composition and attribution, not independent model attack quality.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from gauntlet.analysis import GitRepositoryInspector
from gauntlet.application.gate import PlanChangeDependencies, PlanChangeUseCase
from gauntlet.contracts import ChangeImpactMap, ChangeRequest, RunEvent
from gauntlet.integrations.fake.storage import FakeRunStore
from gauntlet.planning import AttackPlanner, FrozenPlan, PlanningLimits
from gauntlet.ports.model import ModelRequest, ModelResponse
from gauntlet.verification.registry import RegisteredOracleRegistry


def _scripted_attack(change: ChangeRequest, impact: ChangeImpactMap) -> dict[str, object] | None:
    surface = next(
        (
            surface
            for kind in ("style", "component", "route")
            for surface in impact.surfaces
            if surface.kind == kind
        ),
        None,
    )
    if surface is None:
        return None
    return {
        "attack_id": "attack-local-checkout-viewport",
        "hypothesis": "A UI change might obstruct Checkout at a narrow viewport",
        "why_this_change": "The cited changed UI surface merits a narrow viewport check",
        "expected_observation": "The primary Checkout action receives the click",
        "source_refs": [surface.source_refs[0].model_dump(mode="json")],
        "worker_kind": "ui",
        "target_id": change.target_id,
        "fixture_id": change.fixture_id,
        "steps": [
            {"action": "navigate", "path": "/checkout"},
            {"action": "resize", "width": 375, "height": 812},
            {"action": "inspect", "target": "checkout-primary-action"},
            {"action": "click", "target": "checkout-primary-action"},
            {"action": "capture", "label": "after-click"},
        ],
        "oracle_ids": ["ui.primary_action_reachable"],
        "max_actions": 10,
        "max_runtime_seconds": 90,
    }


class _ScriptedGateway:
    def __init__(self, attack: dict[str, object] | None) -> None:
        self._attack = attack
        self.calls = 0

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls += 1
        return ModelResponse(
            text=json.dumps({"attacks": [self._attack] if self._attack else []}),
            model_id="scripted-ui-probe",
        )


@dataclass(frozen=True)
class DiagnosticFreeze:
    frozen: FrozenPlan
    events: tuple[RunEvent, ...]
    model_calls: int


async def freeze_diagnostic_plan(
    repository: Path, change: ChangeRequest, *, run_id: str | None = None
) -> DiagnosticFreeze:
    inspector = GitRepositoryInspector({change.repository_id: repository})
    impact = await inspector.inspect_change(change)
    gateway = _ScriptedGateway(_scripted_attack(change, impact))
    oracles = RegisteredOracleRegistry(plans=(), primary_targets={}, evidence=())
    store = FakeRunStore(initial_sequence=0)
    actual_run_id = run_id or f"local-run-{uuid4().hex}"
    use_case = PlanChangeUseCase(
        PlanChangeDependencies(
            inspector=inspector,
            planner=AttackPlanner(
                gateway, oracles, "Synthetic local UI diagnostic", PlanningLimits()
            ),
            store=store,
            clock=lambda: datetime.now(UTC),
            new_event_id=lambda: f"event-{uuid4().hex}",
        )
    )
    frozen = await use_case.execute(actual_run_id, change)
    return DiagnosticFreeze(frozen, await store.list_events(actual_run_id), gateway.calls)
