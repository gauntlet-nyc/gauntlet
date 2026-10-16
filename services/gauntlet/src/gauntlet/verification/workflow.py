"""Hard workflow completion oracle over bound browser click and inspection evidence."""

import hashlib
from collections.abc import Mapping
from typing import Final
from uuid import uuid4

from gauntlet.application.evidence import check_evidence
from gauntlet.application.image_format import valid_screenshot
from gauntlet.contracts import AttackSpec, EvidenceSubject, Observation, OracleVerdict
from gauntlet.contracts.gate import ClickStep, InspectStep, NavigateStep
from gauntlet.domain import OracleKind, OracleOutcome
from gauntlet.ports.artifacts import ArtifactStore
from gauntlet.ports.errors import UnknownOracleError
from gauntlet.ports.oracle import OracleDescriptor

from .stored_browser import _measurement

DESCRIPTOR: Final = OracleDescriptor(
    oracle_id="workflow.completion_marker_visible",
    kind=OracleKind.HARD,
    criterion_version="1.0",
    worker_kinds=frozenset({"workflow"}),
    description="Submit a registered workflow action and inspect its registered completion marker",
)


class WorkflowCompletionOracle:
    """The target registry, never planner/page text, chooses submit and completion IDs."""

    def __init__(self, store: ArtifactStore, *, targets: Mapping[str, tuple[str, str]]) -> None:
        self._store = store
        self._targets = dict(targets)

    @staticmethod
    def _verdict(
        observation: Observation,
        outcome: OracleOutcome,
        observed: str,
        evidence_ids: tuple[str, ...] = (),
    ) -> OracleVerdict:
        return OracleVerdict(
            verdict_id=f"oracle-{uuid4().hex}",
            oracle_id=DESCRIPTOR.oracle_id,
            oracle_kind=OracleKind.HARD,
            criterion_version=DESCRIPTOR.criterion_version,
            observation_id=observation.observation_id,
            outcome=outcome,
            observed=observed,
            expected="Registered submit action receives click, then completion marker is visible",
            evidence_ids=evidence_ids,
        )

    async def _checked_artifact(
        self, artifact_id: str, subject: EvidenceSubject, index: int, media_type: str
    ) -> bytes | None:
        stored = await self._store.get(artifact_id)
        if (
            stored is None
            or stored.binding.evidence.artifact_id != artifact_id
            or (
                not valid_screenshot(stored.content, stored.binding.evidence.media_type)
                if media_type == "image"
                else stored.binding.evidence.media_type != media_type
            )
            or len(stored.content) != stored.binding.byte_size
            or hashlib.sha256(stored.content).hexdigest() != stored.binding.evidence.sha256
            or not (
                await check_evidence(
                    self._store,
                    stored.binding.evidence,
                    subject.model_copy(update={"step_index": index}),
                )
            ).trusted
        ):
            return None
        return stored.content

    async def evaluate(
        self,
        oracle_id: str,
        plan: AttackSpec,
        observation: Observation,
        subject: EvidenceSubject,
    ) -> OracleVerdict:
        if oracle_id != DESCRIPTOR.oracle_id:
            raise UnknownOracleError("oracle ID is not registered")
        inconclusive = OracleOutcome.INCONCLUSIVE
        targets = self._targets.get(plan.target_id)
        if (
            targets is None
            or plan.worker_kind != "workflow"
            or oracle_id not in plan.oracle_ids
            or observation.status != "completed"
            or plan.attack_id != observation.attack_id
            or subject.collector != "browser_collector"
            or subject.step_index is not None
            or subject.observation_id != observation.observation_id
            or subject.environment_id != observation.environment_id
            or subject.source_sha != observation.source_sha
            or subject.fixture_checksum != observation.fixture_checksum
            or observation.evidence_ids
            != tuple(
                dict.fromkeys(e for record in observation.action_log for e in record.evidence_ids)
            )
        ):
            return self._verdict(observation, inconclusive, "Incomplete or unbound workflow")
        submit, complete = targets
        clicks = [
            i
            for i, step in enumerate(plan.steps)
            if isinstance(step, ClickStep) and step.target == submit
        ]
        markers = [
            i
            for i, step in enumerate(plan.steps)
            if isinstance(step, InspectStep) and step.target == complete
        ]
        if (
            len(clicks) != 1
            or len(markers) != 1
            or not clicks[0] < markers[0]
            or clicks[0] < 2
            or not any(isinstance(step, NavigateStep) for step in plan.steps[: clicks[0]])
        ):
            return self._verdict(observation, inconclusive, "Workflow shape is unsupported")
        click_index, marker_index = clicks[0], markers[0]
        if len(observation.action_log) not in (click_index + 1, len(plan.steps)):
            return self._verdict(observation, inconclusive, "Incomplete action sequence")
        for index, record in enumerate(observation.action_log):
            if record.step_index != index or record.action != plan.steps[index].action:
                return self._verdict(observation, inconclusive, "Action sequence differs from plan")
            if index != click_index and record.outcome != "ok":
                return self._verdict(observation, inconclusive, "Workflow action failed")
        click = observation.action_log[click_index]
        if click.outcome not in {"ok", "blocked"} or len(click.evidence_ids) != 2:
            return self._verdict(observation, inconclusive, "Missing click receipt")
        click_bytes = await self._checked_artifact(
            click.evidence_ids[0], subject, click_index, "application/json"
        )
        screenshot = await self._checked_artifact(
            click.evidence_ids[1], subject, click_index, "image"
        )
        if screenshot is None:
            return self._verdict(observation, inconclusive, "Invalid click screenshot")
        click_measurement = (
            _measurement(click_bytes, submit, click=True) if click_bytes is not None else None
        )
        if click_measurement is None:
            return self._verdict(observation, inconclusive, "Invalid click receipt")
        received = click_measurement["received_target"]
        hit = click_measurement["hit_target"]
        if click.outcome == "blocked":
            if received is None or hit != received or received == submit:
                return self._verdict(observation, inconclusive, "Blocked click is not established")
            if len(observation.action_log) != click_index + 1:
                return self._verdict(
                    observation, inconclusive, "Steps continued after blocked submit"
                )
            return self._verdict(
                observation,
                OracleOutcome.FAIL,
                "Registered submit was intercepted",
                (click.evidence_ids[0],),
            )
        if received != submit or hit != submit or len(observation.action_log) != len(plan.steps):
            return self._verdict(observation, inconclusive, "Submit click is not established")
        marker = observation.action_log[marker_index]
        if len(marker.evidence_ids) != 1:
            return self._verdict(observation, inconclusive, "Missing completion inspection")
        marker_bytes = await self._checked_artifact(
            marker.evidence_ids[0], subject, marker_index, "application/json"
        )
        marker_measurement = (
            _measurement(marker_bytes, complete, click=False) if marker_bytes is not None else None
        )
        if marker_measurement is None or marker_measurement["hit_target"] != complete:
            return self._verdict(observation, inconclusive, "Completion marker is not established")
        return self._verdict(
            observation,
            OracleOutcome.PASS,
            "Completion marker visible after registered submit",
            (click.evidence_ids[0], marker.evidence_ids[0]),
        )
