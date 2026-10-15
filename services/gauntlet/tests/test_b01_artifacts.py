"""B-01d: durable local evidence is immutable and independently verifiable."""

import asyncio
import hashlib
from pathlib import Path

import pytest

from gauntlet.application.evidence import check_evidence
from gauntlet.contracts import EvidenceSubject
from gauntlet.integrations.local_artifacts import LocalArtifactStore
from gauntlet.ports import ArtifactRejectedError, ArtifactStore

PNG = b"\x89PNG\r\n\x1a\nsynthetic screenshot"
SUBJECT = EvidenceSubject(
    run_id="run-001",
    attempt_id="attempt-head-1",
    observation_id="observation-1",
    environment_id="environment-1",
    source_sha="a" * 40,
    fixture_checksum="b" * 64,
    step_index=2,
    collector="browser_collector",
)


def test_artifact_survives_reopen_and_checks_against_its_attempt(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    store = LocalArtifactStore(root)
    _: ArtifactStore = store
    binding = asyncio.run(store.put(PNG, "image/png", SUBJECT))

    reopened = LocalArtifactStore(root)
    stored = asyncio.run(reopened.get(binding.evidence.artifact_id))
    assert stored is not None
    assert stored.content == PNG
    assert stored.binding == binding
    assert binding.evidence.sha256 == hashlib.sha256(PNG).hexdigest()
    assert asyncio.run(check_evidence(reopened, binding.evidence, SUBJECT)).trusted

    another_attempt = SUBJECT.model_copy(update={"attempt_id": "attempt-head-2"})
    assert not asyncio.run(check_evidence(reopened, binding.evidence, another_attempt)).trusted


def test_repeated_put_creates_separate_immutable_artifacts(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "evidence")
    first = asyncio.run(store.put(PNG, "image/png", SUBJECT))
    second = asyncio.run(store.put(PNG, "image/png", SUBJECT))
    assert first.evidence.artifact_id != second.evidence.artifact_id
    assert asyncio.run(store.get(first.evidence.artifact_id)).binding == first
    assert asyncio.run(store.get(second.evidence.artifact_id)).binding == second


@pytest.mark.parametrize("content, media_type", [(b"", "image/png"), (PNG, "text/html")])
def test_invalid_artifact_is_not_written(tmp_path: Path, content: bytes, media_type: str) -> None:
    root = tmp_path / "evidence"
    store = LocalArtifactStore(root)
    with pytest.raises(ArtifactRejectedError):
        asyncio.run(store.put(content, media_type, SUBJECT))
    assert not list(root.iterdir())


def test_corrupt_artifact_is_not_trusted(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    store = LocalArtifactStore(root)
    binding = asyncio.run(store.put(PNG, "image/png", SUBJECT))
    artifact_file = next(root.iterdir())
    data = artifact_file.read_bytes()
    artifact_file.write_bytes(data[:-1] + b"X")

    result = asyncio.run(check_evidence(store, binding.evidence, SUBJECT))
    assert not result.trusted
    assert any("hash" in reason for reason in result.reasons)


def test_malformed_artifact_id_cannot_escape_store(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    store = LocalArtifactStore(root)
    outside = tmp_path / "outside"
    outside.write_bytes(b"secret")
    assert asyncio.run(store.get("../outside")) is None
    assert outside.read_bytes() == b"secret"
