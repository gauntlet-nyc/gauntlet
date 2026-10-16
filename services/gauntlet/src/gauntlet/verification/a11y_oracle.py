"""Hard accessibility oracle over stored inspection evidence (P9).

`a11y.primary_action_target`: every inspection of the registered primary action must show a
target of at least 24x24 CSS px (WCAG 2.2 SC 2.5.8) whose centre hit-test returns the action
itself (not covered by another element). Reads only checked, bound artifacts.
"""

import hashlib
from collections.abc import Mapping
from typing import Final
from uuid import uuid4

from gauntlet.application.evidence import check_evidence
from gauntlet.contracts import AttackSpec, EvidenceSubject, Observation, OracleVerdict
from gauntlet.contracts.gate import InspectStep
from gauntlet.domain import OracleKind, OracleOutcome
from gauntlet.ports.artifacts import ArtifactStore
from gauntlet.ports.errors import UnknownOracleError
from gauntlet.ports.oracle import OracleDescriptor

from .stored_browser import _measurement

A11Y_ORACLE_ID: Final = "a11y.primary_action_target"
MIN_TARGET_PX: Final = 24.0

DESCRIPTOR: Final = OracleDescriptor(
    oracle_id=A11Y_ORACLE_ID,
    kind=OracleKind.HARD,
    criterion_version="wcag22-2.5.8-1.0",
    worker_kinds=frozenset({"accessibility"}),
    description=(
        "Inspect the registered primary action: it must be at least 24x24 CSS px and its "
        "centre must not be covered by another element"
    ),
)


class InspectionA11yOracle:
    def __init__(self, store: ArtifactStore, *, primary_targets: Mapping[str, str]) -> None:
        self._store = store
        self._targets = dict(primary_targets)

    def _verdict(
        self, obs: Observation, outcome: OracleOutcome, observed: str, evidence: tuple[str, ...]
    ) -> OracleVerdict:
        return OracleVerdict(
            verdict_id=f"oracle-{uuid4().hex}",
            oracle_id=A11Y_ORACLE_ID,
            oracle_kind=OracleKind.HARD,
            criterion_version=DESCRIPTOR.criterion_version,
            observation_id=obs.observation_id,
            outcome=outcome,
            observed=observed[:2000],
            expected="Primary action is >= 24x24 px and receives its own centre hit-test",
            evidence_ids=evidence,
        )

    async def evaluate(
        self, oracle_id: str, plan: AttackSpec, observation: Observation, subject: EvidenceSubject
    ) -> OracleVerdict:
        if oracle_id != A11Y_ORACLE_ID:
            raise UnknownOracleError("oracle ID is not registered")
        target = self._targets.get(plan.target_id)
        inconclusive = OracleOutcome.INCONCLUSIVE
        if (
            target is None
            or observation.status != "completed"
            or subject.collector != "browser_collector"
            or len(observation.action_log) != len(plan.steps)
        ):
            return self._verdict(observation, inconclusive, "Incomplete attempt", ())
        problems: list[str] = []
        evidence: list[str] = []
        for index, (step, record) in enumerate(
            zip(plan.steps, observation.action_log, strict=True)
        ):
            if not (isinstance(step, InspectStep) and step.target == target):
                continue
            if record.step_index != index or record.action != "inspect" or not record.evidence_ids:
                return self._verdict(observation, inconclusive, "Missing inspection", ())
            artifact_id = record.evidence_ids[0]
            stored = await self._store.get(artifact_id)
            expected = subject.model_copy(update={"step_index": index})
            if (
                stored is None
                or hashlib.sha256(stored.content).hexdigest() != stored.binding.evidence.sha256
                or not (
                    await check_evidence(self._store, stored.binding.evidence, expected)
                ).trusted
            ):
                return self._verdict(observation, inconclusive, "Inspection failed checks", ())
            measured = _measurement(stored.content, target, click=False)
            if measured is None:
                return self._verdict(observation, inconclusive, "Inspection is malformed", ())
            rect = measured["rect"]
            assert isinstance(rect, Mapping)
            width, height = float(rect["width"]), float(rect["height"])
            evidence.append(artifact_id)
            if width < MIN_TARGET_PX or height < MIN_TARGET_PX:
                problems.append(f"target is {width:.0f}x{height:.0f} px")
            if measured["hit_target"] != target:
                problems.append(f"centre is covered by {measured['hit_target']}")
        if not evidence:
            return self._verdict(observation, inconclusive, "Primary action never inspected", ())
        if problems:
            return self._verdict(
                observation, OracleOutcome.FAIL, "; ".join(problems), (evidence[0],)
            )
        return self._verdict(
            observation, OracleOutcome.PASS, "Primary action is reachable", (evidence[0],)
        )
