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


_REF_FIELDS = tuple(EvidenceRef.model_fields)
_SUBJECT_FIELDS = tuple(EvidenceSubject.model_fields)


async def check_evidence(
    store: ArtifactStore,
    ref: EvidenceRef,
    expected: EvidenceSubject,
) -> EvidenceCheck:
    stored = await store.get(ref.artifact_id)
    if stored is None:
        return EvidenceCheck(ref.artifact_id, ("artifact is missing",))
    reasons: list[str] = []
    binding = stored.binding
    if hashlib.sha256(stored.content).hexdigest() != binding.evidence.sha256:
        reasons.append("stored bytes do not match the recorded hash")
    if len(stored.content) != binding.byte_size:
        reasons.append("stored size differs from the binding")
    # The whole reference must equal the stored one: a producer cannot alter any field.
    for field in _REF_FIELDS:
        if getattr(ref, field) != getattr(binding.evidence, field):
            reasons.append(f"reference {field} differs from the stored binding")
    # Exact subject equality: None is a value, not a wildcard.
    for field in _SUBJECT_FIELDS:
        if getattr(binding.subject, field) != getattr(expected, field):
            reasons.append(f"evidence is bound to a different {field}")
    return EvidenceCheck(ref.artifact_id, tuple(reasons))


async def check_all(
    store: ArtifactStore, refs: Sequence[EvidenceRef], expected: EvidenceSubject
) -> tuple[EvidenceCheck, ...]:
    return tuple([await check_evidence(store, ref, expected) for ref in refs])
