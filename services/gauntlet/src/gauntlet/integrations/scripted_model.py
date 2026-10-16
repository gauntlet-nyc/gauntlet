"""OFFLINE scripted stand-in for the planner model. Labeled ``scripted-offline-planner``.

It reads only what a real model would receive (the planner's untrusted JSON payload) plus an
operator-registered probe description, and proposes fixed-shape attacks. It is a composition
check, not evidence of model attack quality. The validator still decides what is accepted.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from gauntlet.ports.model import ModelRequest, ModelResponse

MODEL_ID = "scripted-offline-planner"


@dataclass(frozen=True)
class UiProbe:
    """Operator registration: which route holds the target's primary action."""

    route: str
    primary_test_id: str
    oracle_id: str = "ui.primary_action_reachable"
    widths: tuple[int, ...] = (375,)
    accessibility: bool = False
    """Also propose the accessibility target-size probe (P9 worker)."""


@dataclass(frozen=True)
class AgentProbe:
    """Operator registration: a synthetic agent and the cross-owner request to try."""

    agent_id: str
    attacker_actor_id: str
    message: str
    oracle_id: str


_UI_SURFACES = ("style", "component", "route")


def _first_ref(impact: Mapping[str, object], kinds: Sequence[str]) -> dict[str, object] | None:
    surfaces = impact.get("surfaces")
    if not isinstance(surfaces, list):
        return None
    for kind in kinds:
        for surface in surfaces:
            if isinstance(surface, dict) and surface.get("kind") == kind:
                refs = surface.get("source_refs")
                if isinstance(refs, list) and refs and isinstance(refs[0], dict):
                    return refs[0]
    return None


class ScriptedModelGateway:
    label = "offline_scripted"

    def __init__(self, ui: UiProbe | None = None, agent: AgentProbe | None = None) -> None:
        self._ui = ui
        self._agent = agent
        self.calls = 0

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls += 1
        try:
            payload = json.loads(request.user)
        except json.JSONDecodeError:
            return ModelResponse(text='{"attacks": []}', model_id=MODEL_ID)
        change = payload.get("change", {})
        impact = payload.get("impact_map", {})
        allowed = set(payload.get("allowed_worker_kinds", ()))
        oracles = {o.get("oracle_id") for o in payload.get("registered_oracles", ())}
        attacks: list[dict[str, object]] = []
        ui_ref = _first_ref(impact, _UI_SURFACES)
        if self._ui and ui_ref and "ui" in allowed and self._ui.oracle_id in oracles:
            for width in self._ui.widths:
                attacks.append(
                    {
                        "attack_id": f"attack-ui-primary-action-{width}",
                        "hypothesis": "A changed UI element may cover the primary action "
                        "at a narrow viewport",
                        "why_this_change": "The cited change alters layout or positioned UI",
                        "expected_observation": "The primary action receives a real click",
                        "source_refs": [ui_ref],
                        "worker_kind": "ui",
                        "target_id": change.get("target_id"),
                        "fixture_id": change.get("fixture_id"),
                        "steps": [
                            {"action": "navigate", "path": self._ui.route},
                            {"action": "resize", "width": width, "height": 812},
                            {"action": "inspect", "target": self._ui.primary_test_id},
                            {"action": "click", "target": self._ui.primary_test_id},
                            {"action": "capture", "label": "after-click"},
                        ],
                        "oracle_ids": [self._ui.oracle_id],
                        "max_actions": 10,
                        "max_runtime_seconds": 90,
                    }
                )
        a11y = "a11y.primary_action_target"
        if (
            self._ui
            and self._ui.accessibility
            and ui_ref
            and "accessibility" in allowed
            and a11y in oracles
        ):
            attacks.append(
                {
                    "attack_id": "attack-a11y-primary-action-target",
                    "hypothesis": "A changed UI element may leave the primary action too small "
                    "or partly covered for touch users",
                    "why_this_change": "The cited change alters layout or positioned UI",
                    "expected_observation": "Primary action is at least 24x24 px and uncovered",
                    "source_refs": [ui_ref],
                    "worker_kind": "accessibility",
                    "target_id": change.get("target_id"),
                    "fixture_id": change.get("fixture_id"),
                    "steps": [
                        {"action": "navigate", "path": self._ui.route},
                        {"action": "resize", "width": 320, "height": 640},
                        {"action": "inspect", "target": self._ui.primary_test_id},
                    ],
                    "oracle_ids": [a11y],
                    "max_actions": 5,
                    "max_runtime_seconds": 60,
                }
            )
        # Memory-informed planning: a verified past occlusion widens the viewport sweep.
        memory = [m for m in payload.get("verified_memory", ()) if isinstance(m, dict)]
        occlusions = [m for m in memory if m.get("kind") == "ui_occlusion"]
        if self._ui and ui_ref and "ui" in allowed and occlusions and attacks:
            fact = occlusions[0]
            remembered = dict(next(a for a in attacks if a["worker_kind"] == "ui"))
            remembered.update(
                {
                    "attack_id": "attack-ui-primary-action-768-memory",
                    "hypothesis": "A positioned element may cover the primary action at a "
                    "tablet viewport as well",
                    "why_this_change": f"Cited change alters UI; verified memory "
                    f"{fact.get('fact_id')} recorded a primary-action occlusion before",
                    "steps": [
                        {"action": "navigate", "path": self._ui.route},
                        {"action": "resize", "width": 768, "height": 1024},
                        {"action": "inspect", "target": self._ui.primary_test_id},
                        {"action": "click", "target": self._ui.primary_test_id},
                        {"action": "capture", "label": "after-click"},
                    ],
                }
            )
            attacks.append(remembered)
        agent_ref = _first_ref(impact, ("agent_tool", "api"))
        if self._agent and agent_ref and "ai_agent" in allowed and self._agent.oracle_id in oracles:
            attacks.append(
                {
                    "attack_id": "attack-ai-cross-owner-refund",
                    "hypothesis": "A changed tool authorization path may let one customer "
                    "refund another customer's order through the assistant",
                    "why_this_change": "The cited change touches the tool's ownership check",
                    "expected_observation": "No refund side effect on an order the actor "
                    "does not own",
                    "source_refs": [agent_ref],
                    "worker_kind": "ai_agent",
                    "target_id": change.get("target_id"),
                    "fixture_id": change.get("fixture_id"),
                    "steps": [
                        {
                            "action": "chat",
                            "agent_id": self._agent.agent_id,
                            "actor_id": self._agent.attacker_actor_id,
                            "message": self._agent.message,
                        }
                    ],
                    "oracle_ids": [self._agent.oracle_id],
                    "max_actions": 4,
                    "max_runtime_seconds": 120,
                }
            )
        return ModelResponse(text=json.dumps({"attacks": attacks}), model_id=MODEL_ID)
