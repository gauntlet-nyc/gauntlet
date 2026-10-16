"""Versioned frozen-plan transport; expected identity must come from a trusted caller.

The canonical plan hash is an integrity check, not a signature or permission to execute.
Consumers must still apply their worker/oracle policy and scope before execution.
"""

import json
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gauntlet.contracts import AttackSpec, ChangeImpactMap, ChangeRequest
from gauntlet.contracts.common import Identifier, Sha256Hex, ShortText, UtcDatetime

from .plan_validation import RejectedAttack
from .planner import PLANNER_VERSION, FrozenPlan, compute_plan_hash

MAX_HANDOFF_BYTES = 2_000_000


class _Rejected(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    attack_id: str = Field(min_length=1, max_length=128)
    reasons: tuple[ShortText, ...] = Field(min_length=1, max_length=100)


class _Handoff(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    handoff_version: Literal["1.0"]
    gate_status: Literal["not_tested"]
    run_id: Identifier
    plan_hash: Sha256Hex
    planner_version: Literal["planner.v1"]
    frozen_at: UtcDatetime
    change: ChangeRequest
    impact: ChangeImpactMap
    attacks: tuple[AttackSpec, ...] = Field(max_length=100)
    rejected: tuple[_Rejected, ...]
    model_id: str | None = Field(max_length=2048)
    prompt_sha256: Sha256Hex
    not_tested_reason: ShortText | None

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.planner_version != PLANNER_VERSION:
            raise ValueError("unsupported planner version")
        if (self.change.base_sha, self.change.head_sha) != (
            self.impact.base_sha,
            self.impact.head_sha,
        ):
            raise ValueError("impact revision binding mismatch")
        if any(
            (a.target_id, a.fixture_id) != (self.change.target_id, self.change.fixture_id)
            for a in self.attacks
        ):
            raise ValueError("attack target or fixture binding mismatch")
        if len({a.attack_id for a in self.attacks}) != len(self.attacks):
            raise ValueError("duplicate attack ID")
        if self.attacks and (not self.model_id or self.not_tested_reason is not None):
            raise ValueError("executable plan requires model provenance and no empty-plan reason")
        if not self.attacks and not self.not_tested_reason:
            raise ValueError("empty plan requires not_tested reason")
        if self.plan_hash != compute_plan_hash(self.change, self.impact, self.attacks):
            raise ValueError("canonical plan hash mismatch")
        return self

    def frozen_plan(self) -> FrozenPlan:
        return FrozenPlan(
            run_id=self.run_id,
            plan_hash=self.plan_hash,
            planner_version=self.planner_version,
            frozen_at=self.frozen_at,
            change=self.change,
            impact=self.impact,
            attacks=self.attacks,
            rejected=tuple(RejectedAttack(r.attack_id, r.reasons) for r in self.rejected),
            model_id=self.model_id,
            not_tested_reason=self.not_tested_reason,
        )


def _unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _parse(raw: str) -> _Handoff:
    if len(raw) > MAX_HANDOFF_BYTES or len(raw.encode("utf-8")) > MAX_HANDOFF_BYTES:
        raise ValueError("frozen plan exceeds size limit")
    try:
        json.loads(raw, object_pairs_hook=_unique_keys)
        return _Handoff.model_validate_json(raw, strict=True)
    except (ValueError, RecursionError) as exc:
        # Do not include Pydantic's source excerpts in public errors.
        raise ValueError("invalid frozen plan handoff") from exc


def serialize_frozen_plan(plan: FrozenPlan, *, prompt_sha256: str) -> str:
    """Serialize a validated snapshot, pinning the exact trusted prompt bytes by hash."""
    document = {
        "handoff_version": "1.0",
        "gate_status": "not_tested",
        "run_id": plan.run_id,
        "plan_hash": plan.plan_hash,
        "planner_version": plan.planner_version,
        "frozen_at": plan.frozen_at.isoformat(),
        "change": plan.change.model_dump(mode="json"),
        "impact": plan.impact.model_dump(mode="json"),
        "attacks": [a.model_dump(mode="json") for a in plan.attacks],
        "rejected": [{"attack_id": r.attack_id, "reasons": r.reasons} for r in plan.rejected],
        "model_id": plan.model_id,
        "prompt_sha256": prompt_sha256,
        "not_tested_reason": plan.not_tested_reason,
    }
    return _parse(json.dumps(document)).model_dump_json()


def load_frozen_plan(
    raw: str,
    *,
    expected_change: ChangeRequest,
    expected_plan_hash: str,
    expected_model_id: str | None,
    expected_prompt_sha256: str,
    expected_run_id: str,
) -> FrozenPlan:
    """Load only when independent trusted identity matches; never trust file-supplied expectations.

    Empty plans are returned for reporting only. Use require_executable_plan before dispatch.
    """
    handoff = _parse(raw)
    if (
        handoff.change != expected_change
        or handoff.plan_hash != expected_plan_hash
        or handoff.model_id != expected_model_id
        or handoff.prompt_sha256 != expected_prompt_sha256
        or handoff.run_id != expected_run_id
    ):
        raise ValueError("frozen plan does not match trusted expected identity")
    return handoff.frozen_plan()


def require_executable_plan(plan: FrozenPlan) -> FrozenPlan:
    """Refuse empty snapshots; this check is not execution authorization."""
    if not plan.attacks:
        raise ValueError("frozen plan has no attacks; gate remains not_tested")
    return plan
