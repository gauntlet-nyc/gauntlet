"""Independent evidence check used by oracles/verifiers before trusting any artifact.

Any missing, corrupt or mismatched evidence yields reasons; the caller must then treat the
oracle result as inconclusive. Nothing here trusts the hash or identity the producer claims.
"""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass

from gauntlet.contracts import EvidenceRef
from gauntlet.contracts.evidence import EvidenceSubject
from gauntlet.ports.artifacts import ArtifactStore


@dataclass(frozen=True)
class EvidenceCheck:
    artifact_id: str
    reasons: tuple[str, ...]

    @property
    def trusted(self) -> bool:
        return not self.reasons


_IDENTITY_FIELDS = (
    "run_id", "attempt_id", "observation_id", "environment_id", "source_sha", "fixture_checksum",
)  # fmt: skip


async def check_evidence(
    store: ArtifactStore,
    ref: EvidenceRef,
    expected: EvidenceSubject,
) -> EvidenceCheck:
    stored = await store.get(ref.artifact_id)
    if stored is None:
        return EvidenceCheck(ref.artifact_id, ("artifact is missing",))
    reasons: list[str] = []
    actual = hashlib.sha256(stored.content).hexdigest()
    binding = stored.binding
    if actual != binding.evidence.sha256:
        reasons.append("stored bytes do not match the recorded hash")
    if ref.sha256 != binding.evidence.sha256:
        reasons.append("reference hash differs from the stored binding")
    if len(stored.content) != binding.byte_size:
        reasons.append("stored size differs from the binding")
    if ref.media_type != binding.evidence.media_type:
        reasons.append("reference media type differs from the stored binding")
    for field in _IDENTITY_FIELDS:
        if getattr(binding.subject, field) != getattr(expected, field):
            reasons.append(f"evidence is bound to a different {field}")
    if expected.step_index is not None and binding.subject.step_index != expected.step_index:
        reasons.append("evidence is bound to a different step")
    if binding.subject.collector != expected.collector:
        reasons.append("evidence came from a different collector")
    return EvidenceCheck(ref.artifact_id, tuple(reasons))


async def check_all(
    store: ArtifactStore, refs: Sequence[EvidenceRef], expected: EvidenceSubject
) -> tuple[EvidenceCheck, ...]:
    return tuple([await check_evidence(store, ref, expected) for ref in refs])
