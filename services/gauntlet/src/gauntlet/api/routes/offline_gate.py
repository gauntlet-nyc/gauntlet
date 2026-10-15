"""P0 joint checkpoint: golden plan -> fake worker -> independent oracle -> verdict -> events.

Everything is recorded/offline (B's fakes); no sandbox, browser or provider is contacted. The
route only composes owner modules and never decides a verdict itself.
"""

from dataclasses import replace
from importlib import resources

from fastapi import APIRouter
from pydantic import BaseModel

from gauntlet.contracts import AttackSpec, Observation, RunEvent
from gauntlet.domain import GateEvidence, classify_gate
from gauntlet.integrations.fake.browser import BrowserRecording, FakeBrowserProvider
from gauntlet.integrations.fake.sandbox import FakeSandboxProvider, Fixture
from gauntlet.integrations.fake.storage import FakeRunStore
from gauntlet.verification.registry import ClickEvidence, RegisteredOracleRegistry
from gauntlet.workers.ui import UIWorker

router = APIRouter()

FIXTURES = resources.files("gauntlet.api").joinpath("fixtures")
PRIMARY_ACTION = "checkout-primary-action"
# (source sha in the golden recording, whether the click is intercepted by the Help button)
RUNS = (("head", "aaaaaaaa", True), ("head", "aaaaaaaa", True), ("base", "bbbbbbbb", False))


class OfflineGateResponse(BaseModel):
    label: str
    execution_mode: str
    oracle_outcomes: tuple[str, ...]
    status: str
    attribution: str
    events: tuple[RunEvent, ...]


async def run_offline_gate() -> OfflineGateResponse:
    plan = AttackSpec.model_validate_json(FIXTURES.joinpath("ui-plan.v1.json").read_bytes())
    template = Observation.model_validate_json(
        FIXTURES.joinpath("observation.v1.json").read_bytes()
    )
    checksum = template.fixture_checksum
    shas = frozenset(sha for _, sha, _ in RUNS)
    sandbox = FakeSandboxProvider({plan.target_id: Fixture(plan.fixture_id, checksum, shas)})
    targets = {plan.target_id: PRIMARY_ACTION}
    outcomes: list[str] = []
    for _, source, intercepted in RUNS:
        env = await sandbox.create(
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
            browser = FakeBrowserProvider((BrowserRecording(plan, source, checksum, records),))
            worker_oracles = RegisteredOracleRegistry(
                plans=(plan,), primary_targets=targets, evidence=()
            )
            obs = await UIWorker(browser, worker_oracles).run(plan, env)
            proof = ClickEvidence(
                "art-shot-001",
                obs.observation_id,
                obs.attack_id,
                env.environment_id,
                source,
                checksum,
                3,
                PRIMARY_ACTION,
                "floating-help-button",
                "floating-help-button",
            )
            if not intercepted:
                proof = replace(proof, hit_target=PRIMARY_ACTION, received_target=PRIMARY_ACTION)
            oracle = RegisteredOracleRegistry(
                plans=(plan,), primary_targets=targets, evidence=(proof,)
            )
            outcomes.append(oracle.evaluate("ui.primary_action_reachable", obs).outcome)
        finally:
            await sandbox.destroy(env.environment_id)
    head = outcomes[:2]
    verdict = classify_gate(
        GateEvidence(
            environment_ok=True,
            fixtures_equal=True,
            oracle_trusted=True,
            head_attempts=len(head),
            head_failures=head.count("fail"),
            base_attempts=1,
            base_failures=outcomes[2:].count("fail"),
        )
    )
    store = FakeRunStore(initial_sequence=1)
    planned = RunEvent.model_validate_json(FIXTURES.joinpath("run-event.v1.json").read_bytes())
    await store.append_event(planned)
    await store.append_event(
        planned.model_copy(
            update={
                "event_id": "event-002",
                "sequence": 2,
                "idempotency_key": f"{planned.run_id}:verified",
                "event_type": "verification_complete",
                "payload": {"status": verdict.status.value, "execution_mode": "offline_recording"},
            }
        )
    )
    return OfflineGateResponse(
        label="OFFLINE RECORDING: replayed golden observations, no browser or sandbox was run",
        execution_mode="offline_recording",
        oracle_outcomes=tuple(outcomes),
        status=verdict.status.value,
        attribution=str(verdict.attribution),
        events=tuple(await store.list_events(planned.run_id, after_sequence=0)),
    )


@router.get("/runs/offline-gate")
async def offline_gate() -> OfflineGateResponse:
    return await run_offline_gate()
