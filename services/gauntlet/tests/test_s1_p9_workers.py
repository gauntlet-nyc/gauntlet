"""P9 workers: accessibility over the browser port and API over an origin-locked client."""

import asyncio
from pathlib import Path

import httpx
import pytest

from gauntlet.contracts import ApiRequestStep, AttackSpec, EvidenceSubject
from gauntlet.domain import OracleOutcome
from gauntlet.integrations.fake.simulated_api import cartwheel_orders_transport
from gauntlet.integrations.http_api import HttpxApiClient
from gauntlet.integrations.local_artifacts import LocalArtifactStore
from gauntlet.ports.sandbox import EnvironmentHandle
from gauntlet.verification.api_oracle import DESCRIPTOR, ApiContractOracle
from gauntlet.verification.catalog import OracleCatalog
from gauntlet.workers.api import ApiWorker
from gauntlet.workers.ui import UIWorker

ENV = EnvironmentHandle(
    environment_id="env-api",
    target_id="cartwheel-fixture",
    source_sha="a" * 40,
    fixture_id="baseline-v1",
    fixture_checksum="b" * 64,
    preview_origin="https://fake-preview.invalid",
)
SUBJECT = EvidenceSubject(
    run_id="run-api",
    attempt_id="attempt-api",
    observation_id="obs-api",
    environment_id=ENV.environment_id,
    source_sha=ENV.source_sha,
    fixture_checksum=ENV.fixture_checksum,
    collector="api_collector",
)


def attack(*bodies: str) -> AttackSpec:
    return AttackSpec(
        attack_id="attack-api",
        hypothesis="h",
        why_this_change="w",
        expected_observation="e",
        source_refs=(
            {
                "path": "src/app/api/orders/route.ts",
                "sha": "a" * 40,
                "start_line": 1,
                "end_line": 2,
            },
        ),  # type: ignore[arg-type]  # fmt: skip
        worker_kind="api",
        target_id=ENV.target_id,
        fixture_id=ENV.fixture_id,
        steps=tuple(
            ApiRequestStep(method="POST", path="/api/orders", actor_id="owner-alice", body_json=b)
            for b in bodies
        ),
        oracle_ids=(DESCRIPTOR.oracle_id,),
        max_actions=5,
        max_runtime_seconds=30,
    )


def outcome(tmp_path: Path, transport: httpx.MockTransport, spec: AttackSpec) -> OracleOutcome:
    async def go() -> OracleOutcome:
        store = LocalArtifactStore(tmp_path / "ev")
        worker = ApiWorker(
            HttpxApiClient(store, transport=transport), OracleCatalog([], DESCRIPTOR)
        )
        obs = await worker.run(spec, ENV, SUBJECT)
        assert obs.status == "completed"
        verdict = await ApiContractOracle(store).evaluate(DESCRIPTOR.oracle_id, spec, obs, SUBJECT)
        return verdict.outcome

    return asyncio.run(go())


VALID = '{"item_id": "demo-wheel", "quantity": 1}'
INVALID = '{"item_id": "demo-wheel", "quantity": 1000}'


def test_api_contract_holds_on_the_real_validator(tmp_path: Path) -> None:
    assert outcome(tmp_path, cartwheel_orders_transport(), attack(VALID, INVALID)) is (
        OracleOutcome.PASS
    )


def test_api_contract_fails_when_invalid_orders_are_accepted(tmp_path: Path) -> None:
    broken = cartwheel_orders_transport(accept_invalid=True)
    assert outcome(tmp_path, broken, attack(VALID, INVALID)) is OracleOutcome.FAIL


def test_api_client_never_follows_redirects(tmp_path: Path) -> None:
    redirect = httpx.MockTransport(
        lambda r: httpx.Response(302, headers={"location": "https://evil.example/x"})
    )
    store = LocalArtifactStore(tmp_path / "ev")
    record = asyncio.run(
        HttpxApiClient(store, transport=redirect).request(
            ENV,
            SUBJECT,
            0,
            attack(VALID).steps[0],  # type: ignore[arg-type]
        )
    )
    assert record.outcome == "blocked"


def test_browser_worker_kinds_are_bounded() -> None:
    with pytest.raises(ValueError):
        UIWorker(None, OracleCatalog([]), kind="api")  # type: ignore[arg-type]


def test_accessibility_worker_flags_the_covered_primary_action(tmp_path: Path) -> None:
    import subprocess
    import sys

    from gauntlet.composition import GateTarget, build_gate
    from gauntlet.domain import GateStatus
    from gauntlet.settings import Settings

    root = Path(__file__).resolve().parents[3]
    repo = tmp_path / "cartwheel"
    subprocess.run(
        [sys.executable, "scripts/build_cartwheel_fixture.py", "--dest", str(repo)],
        cwd=root,
        check=True,
        capture_output=True,
    )
    target = GateTarget.cartwheel(repo)

    async def go() -> list[tuple[str, GateStatus]]:
        runtime = await build_gate(
            Settings.from_env({}), target, model="scripted", sandbox="fake", browser="fake",
            artifact_root=tmp_path / "ev", accessibility_probe=True,
        )  # fmt: skip
        try:
            report = await runtime.use_case.execute(
                "run-a11y", target.change(intent="x"), target.fixture_checksum
            )
        finally:
            await runtime.aclose()
        return [(o.attack.worker_kind, o.finding.status) for o in report.outcomes]

    assert asyncio.run(go()) == [
        ("ui", GateStatus.CONFIRMED_REGRESSION),
        ("accessibility", GateStatus.CONFIRMED_REGRESSION),
    ]
