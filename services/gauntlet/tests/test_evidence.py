"""Issue #22: evidence is write-once, hashed by the store, bound to one attempt, and any
missing/corrupt/mismatched artifact is reported so the oracle can return inconclusive."""

import asyncio
import hashlib
import itertools
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from gauntlet.application.evidence import check_all, check_evidence
from gauntlet.contracts import (
    EVIDENCE_MEDIA_TYPES,
    EvidenceBinding,
    EvidenceRef,
    EvidenceSubject,
)
from gauntlet.contracts.evidence import MAX_EVIDENCE_BYTES
from gauntlet.ports import ArtifactRejectedError, ArtifactStore, StoredArtifact

NOW = datetime(2026, 10, 14, 19, 0, tzinfo=UTC)
PNG = b"\x89PNG\r\n\x1a\n" + b"fake-screenshot-bytes"
SUBJECT = EvidenceSubject(
    run_id="run-001",
    attempt_id="attempt-head-1",
    observation_id="obs-ui-head-001",
    environment_id="env-head-001",
    source_sha="aaaaaaaa",
    fixture_checksum="0f" * 32,
    step_index=3,
    collector="browser_collector",
)


class WriteOnceStore:
    """Reference behaviour for B's adapter: store hashes, assigns IDs, never overwrites."""

    def __init__(self) -> None:
        self.items: dict[str, StoredArtifact] = {}
        self._ids = (f"art-{n:04d}" for n in itertools.count(1))

    async def put(
        self, content: bytes, media_type: str, subject: EvidenceSubject
    ) -> EvidenceBinding:
        if media_type not in EVIDENCE_MEDIA_TYPES or not content:
            raise ArtifactRejectedError("rejected")
        if len(content) > MAX_EVIDENCE_BYTES:
            raise ArtifactRejectedError("too large")
        artifact_id = next(self._ids)
        binding = EvidenceBinding(
            evidence=EvidenceRef(
                artifact_id=artifact_id,
                sha256=hashlib.sha256(content).hexdigest(),
                media_type=media_type,
                created_at=NOW,
            ),
            subject=subject,
            byte_size=len(content),
            recorded_at=NOW,
        )
        self.items[artifact_id] = StoredArtifact(binding, content)
        return binding

    async def get(self, artifact_id: str) -> StoredArtifact | None:
        return self.items.get(artifact_id)


def store_one() -> tuple[WriteOnceStore, EvidenceBinding]:
    store = WriteOnceStore()
    _: ArtifactStore = store  # structural conformance
    return store, asyncio.run(store.put(PNG, "image/png", SUBJECT))


def check(store: WriteOnceStore, ref: EvidenceRef, expected: EvidenceSubject = SUBJECT) -> str:
    return "; ".join(asyncio.run(check_evidence(store, ref, expected)).reasons)


def test_untouched_evidence_is_trusted() -> None:
    store, binding = store_one()
    result = asyncio.run(check_evidence(store, binding.evidence, SUBJECT))
    assert result.trusted
    assert binding.evidence.sha256 == hashlib.sha256(PNG).hexdigest(), "store computed hash"


def test_missing_artifact_is_not_trusted() -> None:
    store, binding = store_one()
    ghost = binding.evidence.model_copy(update={"artifact_id": "art-9999"})
    assert check(store, ghost) == "artifact is missing"


def test_tampered_bytes_are_detected() -> None:
    store, binding = store_one()
    original = store.items[binding.evidence.artifact_id]
    store.items[binding.evidence.artifact_id] = StoredArtifact(original.binding, PNG + b"edit")
    reasons = check(store, binding.evidence)
    assert "do not match the recorded hash" in reasons and "size differs" in reasons


def test_producer_claimed_hash_cannot_override_stored_binding() -> None:
    store, binding = store_one()
    forged = binding.evidence.model_copy(update={"sha256": "bb" * 32})
    assert "reference sha256 differs" in check(store, forged)


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("attempt_id", "attempt-head-2", "different attempt_id"),
        ("run_id", "run-002", "different run_id"),
        ("observation_id", "obs-other", "different observation_id"),
        ("source_sha", "bbbbbbbb", "different source_sha"),
        ("fixture_checksum", "1f" * 32, "different fixture_checksum"),
        ("step_index", 4, "different step_index"),
        ("collector", "replay_collector", "different collector"),
    ],
)
def test_evidence_cannot_be_reused_for_another_attempt(
    field: str, value: object, expected: str
) -> None:
    store, binding = store_one()
    other = SUBJECT.model_copy(update={field: value})
    assert expected in check(store, binding.evidence, other)


def test_check_all_reports_each_artifact() -> None:
    store, binding = store_one()
    ghost = binding.evidence.model_copy(update={"artifact_id": "art-9999"})
    results = asyncio.run(check_all(store, [binding.evidence, ghost], SUBJECT))
    assert [r.trusted for r in results] == [True, False]


@pytest.mark.parametrize(
    ("content", "media_type"),
    [(b"", "image/png"), (PNG, "text/html"), (PNG, "application/x-sh")],
)
def test_store_rejects_empty_or_disallowed_content(content: bytes, media_type: str) -> None:
    with pytest.raises(ArtifactRejectedError):
        asyncio.run(WriteOnceStore().put(content, media_type, SUBJECT))


def test_binding_contract_rejects_bad_media_time_and_unknown_collector() -> None:
    _, binding = store_one()
    data = binding.model_dump()
    with pytest.raises(ValidationError):
        EvidenceBinding.model_validate(
            {**data, "evidence": {**data["evidence"], "media_type": "text/html"}}
        )
    with pytest.raises(ValidationError):
        EvidenceBinding.model_validate({**data, "recorded_at": datetime(2026, 1, 1, tzinfo=UTC)})
    with pytest.raises(ValidationError):
        EvidenceSubject.model_validate({**SUBJECT.model_dump(), "collector": "planner"})


# --- Regressions from B and C review of #26 -------------------------------------------------


def test_any_reference_field_change_is_untrusted() -> None:
    store, binding = store_one()
    later = binding.evidence.created_at.replace(second=1)
    assert "reference created_at differs" in check(
        store, binding.evidence.model_copy(update={"created_at": later})
    )
    assert "reference trace_id differs" in check(
        store, binding.evidence.model_copy(update={"trace_id": "trace-other"})
    )


def test_store_returning_a_different_artifact_is_untrusted() -> None:
    store, binding = store_one()
    other = asyncio.run(store.put(PNG, "image/png", SUBJECT))
    store.items[binding.evidence.artifact_id] = store.items[other.evidence.artifact_id]
    assert "reference artifact_id differs" in check(store, binding.evidence)


def test_unspecified_expected_step_is_not_a_wildcard() -> None:
    store, binding = store_one()
    no_step = SUBJECT.model_copy(update={"step_index": None})
    assert "different step_index" in check(store, binding.evidence, no_step)
