"""B-01d2: the hard UI oracle consumes verified stored browser evidence."""

import asyncio
import json
from pathlib import Path

from test_b01_browser_evidence import GEOMETRY, SUBJECT, FakePage

from gauntlet.contracts import ActionRecord, AttackSpec, Observation
from gauntlet.integrations.browser_evidence import BrowserEvidenceCollector
from gauntlet.integrations.local_artifacts import LocalArtifactStore
from gauntlet.ports.artifacts import StoredArtifact
from gauntlet.verification.stored_browser import StoredBrowserOracle

PLAN_PATH = Path(__file__).resolve().parents[3] / "docs/contracts/examples/ui-plan.v1.json"


def plan() -> AttackSpec:
    return AttackSpec.model_validate_json(PLAN_PATH.read_text())


async def recorded_run(
    store: LocalArtifactStore, *, hit: str, received: str | None, trusted: bool = True
) -> Observation:
    collector = BrowserEvidenceCollector(store)
    geometry = {**GEOMETRY, "hit_target": hit}
    inspect = await collector.inspect(FakePage(geometry), "checkout-primary-action", SUBJECT, 2)
    click = await collector.click(
        FakePage(geometry, None, {"received_target": received, "trusted": trusted}),
        "checkout-primary-action",
        SUBJECT,
        3,
    )
    capture = await collector.capture(FakePage(), SUBJECT, 4)
    records = (
        ActionRecord(step_index=0, action="navigate", outcome="ok"),
        ActionRecord(step_index=1, action="resize", outcome="ok"),
        inspect,
        click,
        capture,
    )
    return Observation(
        observation_id=SUBJECT.observation_id,
        attack_id=plan().attack_id,
        environment_id=SUBJECT.environment_id,
        source_sha=SUBJECT.source_sha,
        fixture_checksum=SUBJECT.fixture_checksum,
        status="completed",
        action_log=records,
        evidence_ids=tuple(e for record in records for e in record.evidence_ids),
    )


def oracle(store: LocalArtifactStore) -> StoredBrowserOracle:
    return StoredBrowserOracle(store, primary_targets={plan().target_id: "checkout-primary-action"})


def test_verified_base_pass_and_head_interception_fail(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = LocalArtifactStore(tmp_path / "evidence")
        base = await recorded_run(
            store, hit="checkout-primary-action", received="checkout-primary-action"
        )
        head = await recorded_run(store, hit="help-button", received="help-button")
        base_verdict = await oracle(store).evaluate(
            "ui.primary_action_reachable", plan(), base, SUBJECT
        )
        head_verdict = await oracle(store).evaluate(
            "ui.primary_action_reachable", plan(), head, SUBJECT
        )
        assert base_verdict.outcome == "pass"
        assert head_verdict.outcome == "fail"
        assert base_verdict.oracle_kind == head_verdict.oracle_kind == "hard"
        assert head_verdict.evidence_ids == (head.action_log[3].evidence_ids[0],)

    asyncio.run(scenario())


def test_missing_or_corrupt_screenshot_is_inconclusive(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = LocalArtifactStore(tmp_path / "evidence")
        observation = await recorded_run(store, hit="help-button", received="help-button")
        screenshot_id = observation.action_log[3].evidence_ids[1]
        screenshot_path = tmp_path / "evidence" / f"{screenshot_id}.artifact"
        screenshot_path.unlink()
        missing = await oracle(store).evaluate(
            "ui.primary_action_reachable", plan(), observation, SUBJECT
        )
        assert missing.outcome == "inconclusive"
        observation = await recorded_run(store, hit="help-button", received="help-button")
        click_json_id = observation.action_log[3].evidence_ids[0]
        click_json_path = tmp_path / "evidence" / f"{click_json_id}.artifact"
        original = click_json_path.read_bytes()
        click_json_path.write_bytes(original[:-1] + b"X")
        corrupt = await oracle(store).evaluate(
            "ui.primary_action_reachable", plan(), observation, SUBJECT
        )
        assert corrupt.outcome == "inconclusive"

    asyncio.run(scenario())


def test_wrong_attempt_and_absent_trusted_receipt_are_inconclusive(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = LocalArtifactStore(tmp_path / "evidence")
        observation = await recorded_run(store, hit="help-button", received="help-button")
        wrong_attempt = SUBJECT.model_copy(update={"attempt_id": "attempt-other"})
        mismatch = await oracle(store).evaluate(
            "ui.primary_action_reachable", plan(), observation, wrong_attempt
        )
        assert mismatch.outcome == "inconclusive"
        wrong_source = SUBJECT.model_copy(update={"source_sha": "c" * 40})
        source_mismatch = await oracle(store).evaluate(
            "ui.primary_action_reachable", plan(), observation, wrong_source
        )
        assert source_mismatch.outcome == "inconclusive"
        no_receipt = await recorded_run(store, hit="help-button", received=None)
        absent = await oracle(store).evaluate(
            "ui.primary_action_reachable", plan(), no_receipt, SUBJECT
        )
        assert absent.outcome == "inconclusive"
        untrusted = await recorded_run(
            store, hit="help-button", received="help-button", trusted=False
        )
        untrusted_verdict = await oracle(store).evaluate(
            "ui.primary_action_reachable", plan(), untrusted, SUBJECT
        )
        assert untrusted_verdict.outcome == "inconclusive"
        contradictory = await recorded_run(
            store, hit="help-button", received="checkout-primary-action"
        )
        contradiction = await oracle(store).evaluate(
            "ui.primary_action_reachable", plan(), contradictory, SUBJECT
        )
        assert contradiction.outcome == "inconclusive"

    asyncio.run(scenario())


def test_changed_bytes_between_store_reads_cannot_prove_pass(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = LocalArtifactStore(tmp_path / "evidence")
        observation = await recorded_run(store, hit="help-button", received="help-button")
        click_id = observation.action_log[3].evidence_ids[0]
        click_record = observation.action_log[3].model_copy(update={"outcome": "ok"})
        observation = observation.model_copy(
            update={
                "action_log": (*observation.action_log[:3], click_record, observation.action_log[4])
            }
        )

        class ChangingStore:
            def __init__(self) -> None:
                self.changed = False

            async def get(self, artifact_id: str) -> StoredArtifact | None:
                stored = await store.get(artifact_id)
                if artifact_id == click_id and stored is not None and not self.changed:
                    self.changed = True
                    receipt = json.loads(stored.content)
                    receipt["hit_target"] = "checkout-primary-action"
                    receipt["received_target"] = "checkout-primary-action"
                    return StoredArtifact(stored.binding, json.dumps(receipt).encode())
                return stored

        verdict = await StoredBrowserOracle(
            ChangingStore(), primary_targets={plan().target_id: "checkout-primary-action"}
        ).evaluate("ui.primary_action_reachable", plan(), observation, SUBJECT)
        assert verdict.outcome == "inconclusive"

    asyncio.run(scenario())
