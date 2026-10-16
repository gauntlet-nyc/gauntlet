"""B-01c2: browser measurements are stored with the session's exact step identity."""

import asyncio
import json
from pathlib import Path

import pytest

from gauntlet.application.evidence import check_evidence
from gauntlet.contracts import EvidenceSubject
from gauntlet.integrations.browser_evidence import BrowserEvidenceCollector
from gauntlet.integrations.local_artifacts import LocalArtifactStore
from gauntlet.ports.errors import EnvironmentUnavailableError

SUBJECT = EvidenceSubject(
    run_id="run-browser-1",
    attempt_id="attempt-head-1",
    observation_id="obs-head-1",
    environment_id="env-head-1",
    source_sha="a" * 40,
    fixture_checksum="b" * 64,
    collector="browser_collector",
)
GEOMETRY = {
    "matches": 1,
    "rect": {"x": 20, "y": 700, "width": 140, "height": 44},
    "viewport": {"width": 375, "height": 812},
    "hit_target": "help-button",
}
PNG = b"\x89PNG\r\n\x1a\nsynthetic-browser-image"


class FakeMouse:
    def __init__(self) -> None:
        self.clicks: list[tuple[float, float]] = []

    async def click(self, x: float, y: float) -> None:
        self.clicks.append((x, y))


class FakePage:
    def __init__(self, *evaluations: object) -> None:
        self.evaluations = list(evaluations)
        self.mouse = FakeMouse()

    async def evaluate(self, expression: str, arg: object = None) -> object:
        assert expression
        return self.evaluations.pop(0)

    async def screenshot(self, *, type: str | None = None) -> bytes:
        return PNG if type == "png" else b"\xff\xd8\xff\xe0synthetic-jpeg"


def test_inspection_writes_step_bound_json(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = LocalArtifactStore(tmp_path / "artifacts")
        record = await BrowserEvidenceCollector(store).inspect(
            FakePage(GEOMETRY), "checkout-primary-action", SUBJECT, 2
        )
        assert record.outcome == "ok"
        assert len(record.evidence_ids) == 1
        stored = await store.get(record.evidence_ids[0])
        assert stored is not None
        expected = SUBJECT.model_copy(update={"step_index": 2})
        assert stored.binding.subject == expected
        assert json.loads(stored.content)["hit_target"] == "help-button"
        assert (await check_evidence(store, stored.binding.evidence, expected)).trusted
        other_attempt = expected.model_copy(update={"attempt_id": "attempt-base-1"})
        assert not (await check_evidence(store, stored.binding.evidence, other_attempt)).trusted

    asyncio.run(scenario())


def test_click_writes_actual_recipient_and_png_for_same_step(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = LocalArtifactStore(tmp_path / "artifacts")
        page = FakePage(
            GEOMETRY,
            None,
            {"received_target": "help-button", "trusted": True},
        )
        record = await BrowserEvidenceCollector(store).click(
            page, "checkout-primary-action", SUBJECT, 3
        )
        assert record.outcome == "blocked"
        assert page.mouse.clicks == [(90.0, 722.0)]
        assert len(record.evidence_ids) == 2
        stored = [await store.get(artifact_id) for artifact_id in record.evidence_ids]
        assert all(item is not None for item in stored)
        assert {item.binding.evidence.media_type for item in stored if item} == {
            "application/json",
            "image/png",
        }
        assert all(item.binding.subject.step_index == 3 for item in stored if item)
        assert (
            next(
                item.content
                for item in stored
                if item and item.binding.evidence.media_type == "image/png"
            )
            == PNG
        )
        receipt = next(
            item
            for item in stored
            if item and item.binding.evidence.media_type == "application/json"
        )
        assert json.loads(receipt.content)["received_target"] == "help-button"

    asyncio.run(scenario())


def test_absent_trusted_click_receipt_cannot_pass(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = LocalArtifactStore(tmp_path / "artifacts")
        page = FakePage(GEOMETRY, None, None)
        record = await BrowserEvidenceCollector(store).click(
            page, "checkout-primary-action", SUBJECT, 3
        )
        assert record.outcome == "error"
        assert record.evidence_ids

    asyncio.run(scenario())


def test_boolean_match_count_cannot_drive_click(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = LocalArtifactStore(tmp_path / "artifacts")
        page = FakePage(
            {**GEOMETRY, "matches": True},
            None,
            {"received_target": "checkout-primary-action", "trusted": True},
        )
        record = await BrowserEvidenceCollector(store).click(
            page, "checkout-primary-action", SUBJECT, 3
        )
        assert record.outcome == "error"
        assert page.mouse.clicks == []

    asyncio.run(scenario())


def test_capture_writes_final_state_png_at_its_own_step(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = LocalArtifactStore(tmp_path / "artifacts")
        record = await BrowserEvidenceCollector(store).capture(FakePage(), SUBJECT, 4)
        assert record.action == "capture"
        assert record.outcome == "ok"
        assert len(record.evidence_ids) == 1
        stored = await store.get(record.evidence_ids[0])
        assert stored is not None
        assert stored.content == PNG
        assert stored.binding.subject.step_index == 4

    asyncio.run(scenario())


@pytest.mark.parametrize("action", ["capture", "click"])
def test_non_png_screenshot_is_never_stored_as_png(tmp_path: Path, action: str) -> None:
    class InvalidImagePage(FakePage):
        async def screenshot(self, *, type: str | None = None) -> bytes:
            return b"\xff\xd8\xff\xe0synthetic-jpeg"

    async def scenario() -> None:
        store = LocalArtifactStore(tmp_path / "artifacts")
        collector = BrowserEvidenceCollector(store)
        page = InvalidImagePage(GEOMETRY, None, {"received_target": "help-button", "trusted": True})
        with pytest.raises(EnvironmentUnavailableError):
            if action == "capture":
                await collector.capture(page, SUBJECT, 0)
            else:
                await collector.click(page, "checkout-primary-action", SUBJECT, 0)
        for path in (tmp_path / "artifacts").glob("*.artifact"):
            artifact = await store.get(path.stem)
            assert artifact is not None
            assert artifact.binding.evidence.media_type != "image/png"

    asyncio.run(scenario())
