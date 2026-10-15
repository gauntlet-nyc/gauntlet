"""Turn checked browser artifacts into input for the fixed primary-action oracle.

The observation and page JSON only nominate artifact IDs. This verifier reads
the immutable store, checks byte hashes and exact step subjects, then validates
the collector's measurement format before constructing click evidence.
"""

import hashlib
import json
import math
from collections.abc import Mapping

from gauntlet.application.evidence import check_evidence
from gauntlet.contracts import AttackSpec, EvidenceSubject, Observation, OracleVerdict
from gauntlet.contracts.gate import CaptureStep, ClickStep, InspectStep
from gauntlet.ports.artifacts import ArtifactStore, StoredArtifact

from .registry import ClickEvidence, RegisteredOracleRegistry

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_MAX_MEASUREMENT_BYTES = 64 * 1024


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _selector(value: object) -> bool:
    return isinstance(value, str) and 0 < len(value) <= 512


def _measurement(content: bytes, target: str, *, click: bool) -> dict[str, object] | None:
    if len(content) > _MAX_MEASUREMENT_BYTES:
        return None
    try:
        raw = json.loads(content)
    except (UnicodeDecodeError, ValueError):
        return None
    required = {"target", "rect", "viewport", "hit_target"}
    if click:
        required.update({"received_target", "trusted"})
    if not isinstance(raw, dict) or set(raw) != required or raw["target"] != target:
        return None
    rect, viewport = raw["rect"], raw["viewport"]
    if (
        not isinstance(rect, Mapping)
        or set(rect) != {"x", "y", "width", "height"}
        or not isinstance(viewport, Mapping)
        or set(viewport) != {"width", "height"}
    ):
        return None
    numbers = {key: _finite_number(rect[key]) for key in ("x", "y", "width", "height")}
    width = _finite_number(viewport["width"])
    height = _finite_number(viewport["height"])
    if any(value is None for value in numbers.values()) or width is None or height is None:
        return None
    x, y, rect_width, rect_height = (numbers[key] for key in ("x", "y", "width", "height"))
    assert x is not None and y is not None and rect_width is not None and rect_height is not None
    if (
        rect_width <= 0
        or rect_height <= 0
        or width <= 0
        or height <= 0
        or not 0 <= x + rect_width / 2 < width
        or not 0 <= y + rect_height / 2 < height
    ):
        return None
    hit = raw["hit_target"]
    if hit is not None and not _selector(hit):
        return None
    if click:
        received = raw["received_target"]
        if (received is not None and not _selector(received)) or raw["trusted"] is not True:
            return None
    return raw


class StoredBrowserOracle:
    """Read-only bridge from bound artifacts to the registered hard oracle."""

    def __init__(self, store: ArtifactStore, *, primary_targets: Mapping[str, str]) -> None:
        self._store = store
        self._targets = dict(primary_targets)

    async def evaluate(
        self,
        oracle_id: str,
        plan: AttackSpec,
        observation: Observation,
        subject: EvidenceSubject,
    ) -> OracleVerdict:
        proof = await self._verified_click(plan, observation, subject)
        registry = RegisteredOracleRegistry(
            plans=(plan,),
            primary_targets=self._targets,
            evidence=(proof,) if proof is not None else (),
        )
        return registry.evaluate(oracle_id, observation)

    async def _read_checked(
        self, artifact_id: str, expected: EvidenceSubject
    ) -> StoredArtifact | None:
        try:
            stored = await self._store.get(artifact_id)
            if (
                stored is None
                or stored.binding.evidence.artifact_id != artifact_id
                or len(stored.content) != stored.binding.byte_size
                or hashlib.sha256(stored.content).hexdigest() != stored.binding.evidence.sha256
                or not (
                    await check_evidence(self._store, stored.binding.evidence, expected)
                ).trusted
            ):
                return None
            return stored
        except Exception:
            return None

    async def _verified_click(
        self, plan: AttackSpec, obs: Observation, subject: EvidenceSubject
    ) -> ClickEvidence | None:
        if (
            subject.collector != "browser_collector"
            or subject.step_index is not None
            or subject.observation_id != obs.observation_id
            or subject.environment_id != obs.environment_id
            or subject.source_sha != obs.source_sha
            or subject.fixture_checksum != obs.fixture_checksum
            or plan.attack_id != obs.attack_id
            or len(plan.steps) != len(obs.action_log)
            or obs.evidence_ids
            != tuple(dict.fromkeys(e for record in obs.action_log for e in record.evidence_ids))
        ):
            return None
        primary = self._targets.get(plan.target_id)
        if primary is None:
            return None
        proof: ClickEvidence | None = None
        for index, (step, record) in enumerate(zip(plan.steps, obs.action_log, strict=True)):
            if record.step_index != index or record.action != step.action:
                return None
            expected_media: tuple[str, ...]
            if isinstance(step, InspectStep):
                expected_media = ("application/json",)
            elif isinstance(step, ClickStep):
                expected_media = ("application/json", "image/png")
            elif isinstance(step, CaptureStep):
                expected_media = ("image/png",)
            else:
                expected_media = ()
            if len(record.evidence_ids) != len(expected_media):
                return None
            artifacts: list[StoredArtifact] = []
            for artifact_id, media in zip(record.evidence_ids, expected_media, strict=True):
                stored = await self._read_checked(
                    artifact_id, subject.model_copy(update={"step_index": index})
                )
                if stored is None or stored.binding.evidence.media_type != media:
                    return None
                if media == "image/png" and not stored.content.startswith(_PNG_SIGNATURE):
                    return None
                artifacts.append(stored)
            if isinstance(step, (InspectStep, ClickStep)):
                measurement = _measurement(
                    artifacts[0].content, step.target, click=isinstance(step, ClickStep)
                )
                if measurement is None:
                    return None
                if isinstance(step, ClickStep) and step.target == primary:
                    hit = measurement["hit_target"]
                    received = measurement["received_target"]
                    if (
                        not isinstance(hit, str)
                        or (received is not None and not isinstance(received, str))
                    ):
                        return None
                    proof = ClickEvidence(
                        evidence_id=record.evidence_ids[0],
                        observation_id=obs.observation_id,
                        attack_id=obs.attack_id,
                        environment_id=obs.environment_id,
                        source_sha=obs.source_sha,
                        fixture_checksum=obs.fixture_checksum,
                        step_index=index,
                        target=primary,
                        hit_target=hit,
                        received_target=received,
                    )
        return proof
