"""Write-once evidence storage (issue #22). B implements it (local dir / object store)."""

from dataclasses import dataclass
from typing import Protocol

from gauntlet.contracts import EvidenceBinding, EvidenceSubject


@dataclass(frozen=True)
class StoredArtifact:
    binding: EvidenceBinding
    content: bytes


class ArtifactStore(Protocol):
    async def put(
        self, content: bytes, media_type: str, subject: EvidenceSubject
    ) -> EvidenceBinding:
        """Store bytes once and return the binding. The store assigns `artifact_id`, computes
        SHA-256 from `content` itself and timestamps it. Never overwrites; raise
        ArtifactRejectedError for disallowed media types, empty or oversized content."""
        ...

    async def get(self, artifact_id: str) -> StoredArtifact | None:
        """Return the exact stored bytes and binding, or None. Read-only."""
        ...
