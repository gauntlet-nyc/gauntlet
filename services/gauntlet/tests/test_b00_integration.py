"""Golden input to independent verdict to append-only event, with sockets forbidden."""

import socket
from dataclasses import replace
from pathlib import Path

import pytest
from gauntlet.contracts import AttackSpec, Observation, RunEvent
from gauntlet.domain import GateEvidence, classify_gate
from gauntlet.integrations.fake.browser import BrowserRecording, FakeBrowserProvider
from gauntlet.integrations.fake.sandbox import FakeSandboxProvider, Fixture
from gauntlet.integrations.fake.storage import FakeRunStore
from gauntlet.verification.registry import ClickEvidence, RegisteredOracleRegistry
from gauntlet.workers.ui import UIWorker

GOLDENS = Path(__file__).resolve().parents[3] / "docs/contracts/examples"


@pytest.mark.asyncio
async def test_golden_plan_to_verified_event_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def deny_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("offline integration attempted network access")

    monkeypatch.setattr(socket.socket, "connect", deny_network)
    plan = AttackSpec.model_validate_json((GOLDENS / "ui-plan.v1.json").read_text())
    template = Observation.model_validate_json((GOLDENS / "observation.v1.json").read_text())
    sandbox = FakeSandboxProvider(
        {
            plan.target_id: Fixture(
                plan.fixture_id, template.fixture_checksum, frozenset({"aaaaaaaa", "bbbbbbbb"})
            )
        }
    )
    targets = {plan.target_id: "checkout-primary-action"}
    outcomes = []
    for source, intercepted in (("aaaaaaaa", True), ("aaaaaaaa", True), ("bbbbbbbb", False)):
        environment = await sandbox.create(
            target_id=plan.target_id,
            source_sha=source,
            fixture_id=plan.fixture_id,
            mode="gate_compare",
        )
        try:
            records = template.action_log
            if not intercepted:
                records = (
                    *records[:3],
                    records[3].model_copy(update={"outcome": "ok"}),
                    records[4],
                )
            browser = FakeBrowserProvider(
                (BrowserRecording(plan, source, template.fixture_checksum, records),)
            )
            worker_registry = RegisteredOracleRegistry(
                plans=(plan,), primary_targets=targets, evidence=()
            )
            obs = await UIWorker(browser, worker_registry).run(plan, environment)
            proof = ClickEvidence(
                "art-shot-001",
                obs.observation_id,
                obs.attack_id,
                environment.environment_id,
                source,
                template.fixture_checksum,
                3,
                "checkout-primary-action",
                "floating-help-button",
                "floating-help-button",
            )
            if not intercepted:
                proof = replace(
                    proof,
                    hit_target="checkout-primary-action",
                    received_target="checkout-primary-action",
                )
            oracle = RegisteredOracleRegistry(
                plans=(plan,), primary_targets=targets, evidence=(proof,)
            )
            outcomes.append(oracle.evaluate("ui.primary_action_reachable", obs).outcome)
        finally:
            await sandbox.destroy(environment.environment_id)
        assert not await sandbox.verify_fixture(
            environment.environment_id, template.fixture_checksum
        )
    assert outcomes == ["fail", "fail", "pass"]
    verdict = classify_gate(
        GateEvidence(
            environment_ok=True,
            fixtures_equal=True,
            oracle_trusted=True,
            head_attempts=2,
            head_failures=outcomes[:2].count("fail"),
            base_attempts=1,
            base_failures=outcomes[2:].count("fail"),
        )
    )
    assert verdict.status == "confirmed_regression"
    assert verdict.attribution == "introduced"
    store = FakeRunStore(initial_sequence=1)
    event = RunEvent.model_validate_json((GOLDENS / "run-event.v1.json").read_text())
    await store.append_event(event)
    await store.append_event(
        event.model_copy(
            update={
                "event_id": "event-002",
                "sequence": 2,
                "idempotency_key": "run-001:verified",
                "event_type": "verification_complete",
                "payload": {"status": verdict.status.value, "execution_mode": "offline_recording"},
            }
        )
    )
    stored = await store.list_events("run-001", after_sequence=1)
    assert len(stored) == 1
    assert stored[0].payload == {
        "status": "confirmed_regression",
        "execution_mode": "offline_recording",
    }
