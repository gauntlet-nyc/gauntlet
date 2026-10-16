"""Fixed primary-action oracle with evidence injected by the trusted composition root.

ClickEvidence is internal trusted evidence, never parsed from planner/page text.
P0 supplies synthetic records; P1 constructs records after stored artifact
bindings and collector measurements pass independent verification.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import uuid4

from gauntlet.contracts import AttackSpec, Observation, OracleVerdict
from gauntlet.contracts.gate import ClickStep, InspectStep
from gauntlet.domain import OracleKind, OracleOutcome
from gauntlet.ports.errors import UnknownOracleError
from gauntlet.ports.oracle import OracleDescriptor

_ORACLE_ID = "ui.primary_action_reachable"


@dataclass(frozen=True)
class ClickEvidence:
    evidence_id: str
    observation_id: str
    attack_id: str
    environment_id: str
    source_sha: str
    fixture_checksum: str
    step_index: int
    target: str
    hit_target: str
    received_target: str | None


class RegisteredOracleRegistry:
    def __init__(
        self,
        *,
        plans: tuple[AttackSpec, ...],
        primary_targets: Mapping[str, str],
        evidence: tuple[ClickEvidence, ...],
        primary_routes: Mapping[str, str] | None = None,
    ) -> None:
        self._plans = {plan.attack_id: plan.model_copy(deep=True) for plan in plans}
        self._targets = dict(primary_targets)
        self._routes = dict(primary_routes or {})
        self._evidence = {item.evidence_id: item for item in evidence}
        if len(self._plans) != len(plans) or len(self._evidence) != len(evidence):
            raise ValueError("plan and evidence identities must be unique")

    def is_registered(self, oracle_id: str) -> bool:
        return oracle_id == _ORACLE_ID

    def descriptors(self) -> tuple[OracleDescriptor, ...]:
        return (self.descriptor(_ORACLE_ID),)

    def descriptor(self, oracle_id: str) -> OracleDescriptor:
        if not self.is_registered(oracle_id):
            raise UnknownOracleError("oracle ID is not registered")
        return OracleDescriptor(
            oracle_id=_ORACLE_ID,
            kind=OracleKind.HARD,
            criterion_version="1.0",
            worker_kinds=frozenset({"ui"}),
            description=self._description(),
        )

    def _description(self) -> str:
        text = "Checks whether the registered primary action receives a click"
        if not self._targets:
            return text
        actions = ", ".join(
            f"{t}: data-testid={a}" + (f" on {self._routes[t]}" if t in self._routes else "")
            for t, a in sorted(self._targets.items())
        )
        # Authorized target context and the evidence contract; identifiers only, never logic.
        return (
            f"{text}. Registered primary actions ({actions}). Evidence contract: navigate to the "
            "route that renders the primary action, optionally resize, `inspect` that data-testid, "
            "then `click` it exactly once (a final `capture` is allowed). Every other step must "
            "succeed. Step `target` values are bare data-testid values, never CSS selectors."
        )

    def evaluate(self, oracle_id: str, observation: Observation) -> OracleVerdict:
        kind = self.descriptor(oracle_id).kind
        outcome, evidence_ids = self._evaluate_click(observation)
        return OracleVerdict(
            verdict_id=f"oracle-{uuid4().hex}",
            oracle_id=oracle_id,
            oracle_kind=kind,
            criterion_version="1.0",
            observation_id=observation.observation_id,
            outcome=outcome,
            evidence_ids=evidence_ids,
            observed={
                OracleOutcome.PASS: "Primary action received the recorded click",
                OracleOutcome.FAIL: "Another element intercepted the recorded click",
                OracleOutcome.INCONCLUSIVE: "Complete, consistent click evidence unavailable",
            }[outcome],
            expected="The registered primary action receives the click",
        )

    def _evaluate_click(self, obs: Observation) -> tuple[OracleOutcome, tuple[str, ...]]:
        inconclusive = (OracleOutcome.INCONCLUSIVE, ())
        plan = self._plans.get(obs.attack_id)
        if plan is None or obs.status != "completed" or _ORACLE_ID not in plan.oracle_ids:
            return inconclusive
        target = self._targets.get(plan.target_id)
        if target is None or len(obs.action_log) != len(plan.steps):
            return inconclusive
        clicks = [
            i
            for i, step in enumerate(plan.steps)
            if isinstance(step, ClickStep) and step.target == target
        ]
        if len(clicks) != 1:
            return inconclusive
        index = clicks[0]
        inspected = False
        for i, (step, record) in enumerate(zip(plan.steps, obs.action_log, strict=True)):
            if record.step_index != i or record.action != step.action:
                return inconclusive
            if i != index and record.outcome != "ok":
                return inconclusive
            if (
                i < index
                and isinstance(step, InspectStep)
                and step.target == target
                and record.evidence_ids
                and set(record.evidence_ids).issubset(obs.evidence_ids)
            ):
                inspected = True
        if not inspected:
            return inconclusive
        click = obs.action_log[index]
        proofs = [
            self._evidence[e]
            for e in click.evidence_ids
            if e in self._evidence and e in obs.evidence_ids
        ]
        if len(proofs) != 1:
            return inconclusive
        proof = proofs[0]
        if (
            proof.observation_id,
            proof.attack_id,
            proof.environment_id,
            proof.source_sha,
            proof.fixture_checksum,
            proof.step_index,
            proof.target,
        ) != (
            obs.observation_id,
            obs.attack_id,
            obs.environment_id,
            obs.source_sha,
            obs.fixture_checksum,
            index,
            target,
        ):
            return inconclusive
        if click.outcome == "ok" and proof.received_target == target and proof.hit_target == target:
            return OracleOutcome.PASS, (proof.evidence_id,)
        if (
            click.outcome == "blocked"
            and proof.hit_target
            and proof.hit_target != target
            and proof.received_target == proof.hit_target
        ):
            return OracleOutcome.FAIL, (proof.evidence_id,)
        return inconclusive
