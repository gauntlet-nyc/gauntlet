"""Independent policy check on model-proposed attacks. Everything the model says is untrusted."""

import json
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import ValidationError

from gauntlet.contracts import (
    ApiRequestStep,
    AttackSpec,
    ChangeImpactMap,
    ChangeRequest,
    ChatStep,
    ClickStep,
    InspectStep,
    NavigateStep,
    SourceRef,
)
from gauntlet.ports import TargetProfile, TrustedOracleRegistry
from gauntlet.ports.oracle import PrimaryActionContract, PrimaryActionContractSource

from .worker_selector import allowed_workers


@dataclass(frozen=True)
class PlanningLimits:
    max_attacks: int = 8
    max_total_runtime_seconds: int = 1800
    max_excerpts: int = 12
    max_output_tokens: int = 4000


@dataclass(frozen=True)
class RejectedAttack:
    attack_id: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class PlanValidation:
    accepted: tuple[AttackSpec, ...]
    rejected: tuple[RejectedAttack, ...]


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        stripped = stripped[3:-3]
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else ""
    return stripped


def _overlaps(ref: SourceRef, changed: Sequence[SourceRef]) -> bool:
    return any(
        c.path == ref.path
        and c.sha == ref.sha
        and c.start_line <= ref.end_line
        and ref.start_line <= c.end_line
        for c in changed
    )


class PlanValidator:
    def __init__(self, oracles: TrustedOracleRegistry, limits: PlanningLimits) -> None:
        self._oracles = oracles
        self._limits = limits

    def validate(
        self,
        raw_text: str,
        change: ChangeRequest,
        impact: ChangeImpactMap,
        target: TargetProfile,
    ) -> PlanValidation:
        try:
            document = json.loads(_strip_code_fence(raw_text))
        except json.JSONDecodeError:
            return PlanValidation((), (RejectedAttack("plan", ("model output is not JSON",)),))
        items = document.get("attacks") if isinstance(document, dict) else None
        if not isinstance(items, list):
            return PlanValidation((), (RejectedAttack("plan", ("missing 'attacks' array",)),))

        workers = allowed_workers(impact)
        changed_refs = tuple(ref for s in impact.surfaces for ref in s.source_refs)
        allowed_shas = {impact.base_sha, impact.head_sha}
        accepted: list[AttackSpec] = []
        rejected: list[RejectedAttack] = []
        runtime_used = 0
        seen_ids: set[str] = set()

        for index, item in enumerate(items):
            fallback_id = f"attack[{index}]"
            if len(accepted) >= self._limits.max_attacks:
                rejected.append(RejectedAttack(fallback_id, ("exceeds max_attacks",)))
                continue
            try:
                spec = AttackSpec.model_validate(item)
            except ValidationError as exc:
                errors = tuple(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
                rejected.append(RejectedAttack(fallback_id, errors[:10]))
                continue
            reasons = self._policy_reasons(spec, change, workers, changed_refs, allowed_shas)
            reasons.extend(_step_reasons(spec, target))
            if isinstance(self._oracles, PrimaryActionContractSource):
                for oracle_id in spec.oracle_ids:
                    contract = self._oracles.primary_action_contract(oracle_id, spec.target_id)
                    if contract is not None:
                        reasons.extend(_primary_action_reasons(spec, contract))
            if spec.attack_id in seen_ids:
                reasons.append("duplicate attack_id")
            if runtime_used + spec.max_runtime_seconds > self._limits.max_total_runtime_seconds:
                reasons.append("exceeds total runtime budget")
            if reasons:
                rejected.append(RejectedAttack(spec.attack_id, tuple(reasons)))
                continue
            seen_ids.add(spec.attack_id)
            runtime_used += spec.max_runtime_seconds
            accepted.append(spec)
        return PlanValidation(tuple(accepted), tuple(rejected))

    def _policy_reasons(
        self,
        spec: AttackSpec,
        change: ChangeRequest,
        workers: frozenset[str],
        changed_refs: tuple[SourceRef, ...],
        allowed_shas: set[str],
    ) -> list[str]:
        reasons: list[str] = []
        if spec.target_id != change.target_id:
            reasons.append("target_id does not match the authorized target")
        if spec.fixture_id != change.fixture_id:
            reasons.append("fixture_id does not match the change request")
        if spec.worker_kind not in workers:
            reasons.append(f"worker '{spec.worker_kind}' is not allowed for the changed surfaces")
        for oracle_id in spec.oracle_ids:
            if not self._oracles.is_registered(oracle_id):
                reasons.append(f"oracle '{oracle_id}' is not registered")
            elif spec.worker_kind not in self._oracles.descriptor(oracle_id).worker_kinds:
                reasons.append(f"oracle '{oracle_id}' does not support '{spec.worker_kind}'")
        if any(ref.sha not in allowed_shas for ref in spec.source_refs):
            reasons.append("source_refs must cite the base or head commit")
        if not any(_overlaps(ref, changed_refs) for ref in spec.source_refs):
            reasons.append("no source_ref overlaps a changed line")
        return reasons


def _step_reasons(spec: AttackSpec, target: TargetProfile) -> list[str]:
    """Steps may only use the target's registered routes, synthetic actors and agents."""
    reasons: list[str] = []
    for index, step in enumerate(spec.steps):
        if isinstance(step, NavigateStep | ApiRequestStep) and not target.allows_route(step.path):
            reasons.append(f"step {index}: route is outside the target's registered routes")
        if isinstance(step, ApiRequestStep | ChatStep) and (
            step.actor_id not in target.synthetic_actor_ids
        ):
            reasons.append(f"step {index}: actor is not a registered synthetic identity")
        if isinstance(step, ChatStep) and step.agent_id not in target.agent_ids:
            reasons.append(f"step {index}: agent is not registered for this target")
    return reasons


def _primary_action_reasons(spec: AttackSpec, contract: PrimaryActionContract) -> list[str]:
    """Reject candidates that the hard click oracle could only judge inconclusive."""
    clicks = [
        index
        for index, step in enumerate(spec.steps)
        if isinstance(step, ClickStep) and step.target == contract.target
    ]
    if len(clicks) != 1:
        return ["primary action must be clicked exactly once"]
    click_index = clicks[0]
    preceding = spec.steps[:click_index]
    last_navigation = max(
        (index for index, step in enumerate(preceding) if isinstance(step, NavigateStep)),
        default=-1,
    )
    if last_navigation < 0:
        return ["primary action requires navigation before the click"]
    if contract.route is not None:
        route = spec.steps[last_navigation]
        assert isinstance(route, NavigateStep)
        if route.path.split("?", 1)[0].split("#", 1)[0] != contract.route:
            return ["primary action requires its registered route before the click"]
    if not any(
        isinstance(step, InspectStep) and step.target == contract.target
        for step in preceding[last_navigation + 1 :]
    ):
        return ["primary action requires a matching inspect before the click"]
    return []
