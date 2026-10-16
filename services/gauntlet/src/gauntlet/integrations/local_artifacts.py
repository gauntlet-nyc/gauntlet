"""Local, write-once storage for sanitized evidence captured by trusted collectors."""

import asyncio
import hashlib
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from gauntlet.contracts import EVIDENCE_MEDIA_TYPES, EvidenceBinding, EvidenceRef, EvidenceSubject
from gauntlet.contracts.evidence import MAX_EVIDENCE_BYTES
from gauntlet.ports import ArtifactRejectedError, PortError, StoredArtifact

_ARTIFACT_ID = re.compile(r"art-[0-9a-f]{32}\Z")
_MAX_HEADER_BYTES = 16_384


class LocalArtifactStore:
    """Publish complete evidence as one file; IDs and hashes are assigned here."""

    def __init__(self, root: Path) -> None:
        if root.is_symlink():
            raise PortError("artifact root must not be a symbolic link")
        try:
            root.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as exc:
            raise PortError("artifact root is unavailable") from exc
        if not root.is_dir():
            raise PortError("artifact root is not a directory")
        self._root = root

    async def put(
        self, content: bytes, media_type: str, subject: EvidenceSubject
    ) -> EvidenceBinding:
        if not content or len(content) > MAX_EVIDENCE_BYTES:
            raise ArtifactRejectedError("evidence size is outside the allowed range")
        if media_type not in EVIDENCE_MEDIA_TYPES:
            raise ArtifactRejectedError("evidence media type is not allowed")
        return await asyncio.to_thread(self._put, content, media_type, subject)

    def _put(self, content: bytes, media_type: str, subject: EvidenceSubject) -> EvidenceBinding:
        moment = datetime.now(UTC)
        artifact_id = f"art-{uuid4().hex}"
        binding = EvidenceBinding(
            evidence=EvidenceRef(
                artifact_id=artifact_id,
                sha256=hashlib.sha256(content).hexdigest(),
                media_type=media_type,
                created_at=moment,
            ),
            subject=subject,
            byte_size=len(content),
            recorded_at=moment,
        )
        header = binding.model_dump_json().encode("utf-8")
        if len(header) > _MAX_HEADER_BYTES:
            raise ArtifactRejectedError("evidence binding is too large")
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=self._root, prefix=".pending-", delete=False
            ) as file:
                temporary = Path(file.name)
                file.write(len(header).to_bytes(4, "big"))
                file.write(header)
                file.write(content)
                file.flush()
                os.fsync(file.fileno())
            os.link(temporary, self._root / f"{artifact_id}.artifact")
        except OSError as exc:
            raise PortError("artifact persistence failed") from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return binding

    async def get(self, artifact_id: str) -> StoredArtifact | None:
        if _ARTIFACT_ID.fullmatch(artifact_id) is None:
            return None
        return await asyncio.to_thread(self._get, artifact_id)

    def _get(self, artifact_id: str) -> StoredArtifact | None:
        path = self._root / f"{artifact_id}.artifact"
        try:
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(descriptor, "rb") as file:
                length_bytes = file.read(4)
                if len(length_bytes) != 4:
                    return None
                header_size = int.from_bytes(length_bytes, "big")
                if not 0 < header_size <= _MAX_HEADER_BYTES:
                    return None
                header = file.read(header_size)
                if len(header) != header_size:
                    return None
                content = file.read(MAX_EVIDENCE_BYTES + 1)
                if not content or len(content) > MAX_EVIDENCE_BYTES:
                    return None
            binding = EvidenceBinding.model_validate_json(header)
        except (OSError, ValidationError):
            return None
        if binding.evidence.artifact_id != artifact_id:
            return None
        return StoredArtifact(binding=binding, content=content)
