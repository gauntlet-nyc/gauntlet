"""Independent policy check on model-proposed attacks. Everything the model says is untrusted."""

import json
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import ValidationError

from gauntlet.contracts import AttackSpec, ChangeImpactMap, ChangeRequest, SourceRef
from gauntlet.ports import TrustedOracleRegistry

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
        self, raw_text: str, change: ChangeRequest, impact: ChangeImpactMap
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
