"""In-memory stand-ins for B's persistence, used until SurrealDB-backed stores exist.

State is lost on restart and shared by a single process only. Never used to prove durability.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from gauntlet.contracts import ApprovalRecord, FixPlan
from gauntlet.ports.errors import ApprovalAlreadyConsumedError, DuplicateApprovalError

GOLDENS = Path(__file__).resolve().parents[5] / "docs/contracts/examples"


class InMemoryApprovalStore:
    def __init__(self) -> None:
        self._records: dict[str, ApprovalRecord] = {}
        self._consumed: dict[str, str] = {}

    async def save(self, record: ApprovalRecord) -> None:
        if record.approval_id in self._records:
            raise DuplicateApprovalError("approval id already exists")
        self._records[record.approval_id] = record

    async def get(self, approval_id: str) -> ApprovalRecord | None:
        return self._records.get(approval_id)

    async def consume(self, approval_id: str, consumer_ref: str) -> None:
        if approval_id in self._consumed:
            raise ApprovalAlreadyConsumedError("approval already spent")
        self._consumed[approval_id] = consumer_ref

    def for_subject(self, subject_id: str) -> tuple[ApprovalRecord, ...]:
        return tuple(r for r in self._records.values() if r.subject_id == subject_id)


@dataclass(frozen=True)
class StoredFixPlan:
    plan: FixPlan
    target_id: str
    fixture_id: str


class InMemoryFixPlans:
    """Holds the golden demo fix plan. Real plans come from B's patch runner (B-03)."""

    def __init__(self) -> None:
        plan = FixPlan.model_validate(json.loads((GOLDENS / "fix-plan.v1.json").read_text()))
        self._plans = {plan.fix_plan_id: StoredFixPlan(plan, "cartwheel-fixture", "baseline-v1")}

    def get(self, fix_plan_id: str) -> StoredFixPlan | None:
        return self._plans.get(fix_plan_id)


class DevState:
    def __init__(self) -> None:
        self.approvals = InMemoryApprovalStore()
        self.fix_plans = InMemoryFixPlans()
