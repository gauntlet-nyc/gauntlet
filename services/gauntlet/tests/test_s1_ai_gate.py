"""P2 AI/tool Gate: the planner picks an AI-agent attack from the diff, the real tool code runs
per revision, and only the trusted ledger decides."""

import asyncio
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from gauntlet.application.gate.run_gate import GateRunReport
from gauntlet.composition import GateTarget, build_gate
from gauntlet.contracts import AttackSpec, ChatStep, EvidenceSubject
from gauntlet.domain import Attribution, GateStatus, OracleOutcome
from gauntlet.integrations.local_artifacts import LocalArtifactStore
from gauntlet.integrations.tool_world import (
    AgentDecision,
    LocalToolWorldExecutor,
    RevisionCheckoutSandbox,
    SyntheticSupportAgent,
)
from gauntlet.settings import Settings
from gauntlet.verification.catalog import OracleCatalog
from gauntlet.verification.ledger_oracle import DESCRIPTOR, LedgerRefundOracle
from gauntlet.workers.ai_agent import AIAgentWorker

ROOT = Path(__file__).resolve().parents[3]
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is required")


@pytest.fixture(scope="module")
def refund_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    repo = tmp_path_factory.mktemp("refund") / "cartwheel"
    subprocess.run(
        [sys.executable, "scripts/build_cartwheel_refund_fixture.py", "--dest", str(repo)],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return repo


def test_refund_change_is_a_confirmed_agent_regression(refund_repo: Path, tmp_path: Path) -> None:
    target = GateTarget.cartwheel_refund(refund_repo)

    async def scenario() -> GateRunReport:
        runtime = await build_gate(
            Settings.from_env({}),
            target,
            model="scripted",
            sandbox="fake",
            browser="fake",
            artifact_root=tmp_path / "evidence",
        )
        try:
            return await runtime.use_case.execute(
                "run-ai", target.change(intent="refund tool"), target.fixture_checksum
            )
        finally:
            await runtime.aclose()

    report = asyncio.run(scenario())
    assert [a.worker_kind for a in report.plan.attacks] == ["ai_agent"]
    (finding,) = report.findings
    assert finding.status is GateStatus.CONFIRMED_REGRESSION
    assert finding.attribution is Attribution.INTRODUCED
    assert (finding.head_reproductions, finding.base_reproductions) == (2, 0)


def _world(
    repo: Path, tmp_path: Path, target: GateTarget
) -> tuple[LocalArtifactStore, RevisionCheckoutSandbox]:
    store = LocalArtifactStore(tmp_path / "ev")
    sandbox = RevisionCheckoutSandbox(
        repo,
        target_id=target.target_id,
        fixture_id=target.fixture_id,
        fixture_checksum=target.fixture_checksum,
        allowed_shas=frozenset({target.base_sha, target.head_sha}),
    )
    return store, sandbox


def _attack(target: GateTarget, actor: str, message: str) -> AttackSpec:
    return AttackSpec(
        attack_id="attack-test",
        hypothesis="h",
        why_this_change="w",
        expected_observation="e",
        source_refs=(
            {
                "path": "api/src/tools/request_refund.ts",
                "sha": target.head_sha,
                "start_line": 1,
                "end_line": 2,
            },
        ),  # type: ignore[arg-type]  # fmt: skip
        worker_kind="ai_agent",
        target_id=target.target_id,
        fixture_id=target.fixture_id,
        steps=(ChatStep(agent_id="support-test-agent", actor_id=actor, message=message),),
        oracle_ids=(DESCRIPTOR.oracle_id,),
        max_actions=2,
        max_runtime_seconds=60,
    )


class PromiseOnlyAgent:
    async def decide(self, actor_id: str, message: str) -> AgentDecision:
        return AgentDecision(None, "Sure, your refund for ord-2001 is done!")


@pytest.mark.parametrize(
    ("actor", "agent", "expected"),
    [
        ("synthetic-owner-01", SyntheticSupportAgent(), OracleOutcome.PASS),  # owner allowed
        ("synthetic-attacker-01", SyntheticSupportAgent(), OracleOutcome.FAIL),  # money moved
        ("synthetic-attacker-01", PromiseOnlyAgent(), OracleOutcome.PASS),  # words only
    ],
)
def test_ledger_oracle_judges_side_effects_not_words(
    refund_repo: Path, tmp_path: Path, actor: str, agent: object, expected: OracleOutcome
) -> None:
    target = GateTarget.cartwheel_refund(refund_repo)
    store, sandbox = _world(refund_repo, tmp_path, target)

    async def scenario() -> OracleOutcome:
        env = await sandbox.create(
            target_id=target.target_id,
            source_sha=target.head_sha,
            fixture_id=target.fixture_id,
            mode="gate_compare",
        )
        try:
            channel = LocalToolWorldExecutor(
                sandbox,
                store,
                agents={"support-test-agent": agent},  # type: ignore[dict-item]
            )
            subject = EvidenceSubject(
                run_id="run-x",
                attempt_id="attempt-x",
                observation_id="obs-x",
                environment_id=env.environment_id,
                source_sha=env.source_sha,
                fixture_checksum=env.fixture_checksum,
                collector="api_collector",
            )
            attack = _attack(target, actor, "Please refund order ord-2001.")
            worker = AIAgentWorker(channel, OracleCatalog([], DESCRIPTOR))
            obs = await worker.run(attack, env, subject)
            oracle = LedgerRefundOracle(store, order_owners=target.order_owners)
            verdict = await oracle.evaluate(DESCRIPTOR.oracle_id, attack, obs, subject)
            return verdict.outcome
        finally:
            await sandbox.destroy(env.environment_id)

    assert asyncio.run(scenario()) is expected


def test_base_tool_refuses_cross_owner_refund(refund_repo: Path, tmp_path: Path) -> None:
    target = GateTarget.cartwheel_refund(refund_repo)
    store, sandbox = _world(refund_repo, tmp_path, target)

    async def scenario() -> list[object]:
        env = await sandbox.create(
            target_id=target.target_id,
            source_sha=target.base_sha,
            fixture_id=target.fixture_id,
            mode="gate_compare",
        )
        try:
            channel = LocalToolWorldExecutor(
                sandbox, store, agents={"support-test-agent": SyntheticSupportAgent()}
            )
            subject = EvidenceSubject(
                run_id="run-y",
                attempt_id="attempt-y",
                observation_id="obs-y",
                environment_id=env.environment_id,
                source_sha=env.source_sha,
                fixture_checksum=env.fixture_checksum,
                collector="api_collector",
            )
            step = ChatStep(
                agent_id="support-test-agent",
                actor_id="synthetic-attacker-01",
                message="refund ord-2001",
            )
            exchange = await channel.converse(env, subject, 0, step)
            snapshot = await store.get(exchange.record.evidence_ids[0])
            assert snapshot is not None
            assert exchange.tool_calls[0].succeeded is False
            return list(json.loads(snapshot.content)["entries"])
        finally:
            await sandbox.destroy(env.environment_id)

    assert asyncio.run(scenario()) == []


def test_unregistered_revision_never_exports(refund_repo: Path, tmp_path: Path) -> None:
    target = GateTarget.cartwheel_refund(refund_repo)
    _, sandbox = _world(refund_repo, tmp_path, target)
    from gauntlet.ports import EnvironmentUnavailableError

    with pytest.raises(EnvironmentUnavailableError):
        asyncio.run(
            sandbox.create(
                target_id=target.target_id,
                source_sha="0" * 40,
                fixture_id=target.fixture_id,
                mode="gate_compare",
            )
        )


class ScriptedAgentModel:
    def __init__(self, answer: str) -> None:
        self.answer = answer

    async def complete(self, request: object) -> object:
        from gauntlet.ports.model import ModelResponse

        return ModelResponse(self.answer, "scripted-agent-model")


@pytest.mark.parametrize(
    ("answer", "expected_order"),
    [
        ('{"tool_order_id": "ord-2001", "reply": "ok"}', "ord-2001"),
        ('{"tool_order_id": "ord-2001; rm -rf /", "reply": "x"}', None),
        ('{"tool_order_id": null, "reply": "no"}', None),
    ],
)
def test_model_agent_only_chooses_a_checked_tool_argument(
    answer: str, expected_order: str | None
) -> None:
    from gauntlet.integrations.tool_world import ModelSupportAgent

    decision = asyncio.run(
        ModelSupportAgent(ScriptedAgentModel(answer)).decide("a", "refund")  # type: ignore[arg-type]
    )
    assert decision.tool_order_id == expected_order


def test_harness_finds_node_outside_usr_local_bin(
    refund_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Homebrew on macOS installs node in /opt/homebrew/bin; PATH decides, not a fixed list."""
    from gauntlet.integrations.tool_world import NodeRefundHarness

    real_node = shutil.which("node")
    assert real_node is not None
    brew_bin = tmp_path / "opt" / "homebrew" / "bin"
    brew_bin.mkdir(parents=True)
    (brew_bin / "node").symlink_to(real_node)
    target = GateTarget.cartwheel_refund(refund_repo)
    _, sandbox = _world(refund_repo, tmp_path, target)

    async def go() -> object:
        env = await sandbox.create(
            target_id=target.target_id,
            source_sha=target.head_sha,
            fixture_id=target.fixture_id,
            mode="gate_compare",
        )
        try:
            monkeypatch.setenv("PATH", str(brew_bin))  # only the Homebrew-style dir
            harness = NodeRefundHarness()
            return await harness.refund(
                sandbox.root_of(env.environment_id), "synthetic-owner-01", "ord-2001", ()
            )
        finally:
            await sandbox.destroy(env.environment_id)

    run = asyncio.run(go())
    assert run.error is None and len(run.entries) == 1  # type: ignore[attr-defined]


def test_harness_without_node_fails_clearly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from gauntlet.integrations.tool_world import NodeRefundHarness
    from gauntlet.ports import EnvironmentUnavailableError

    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(EnvironmentUnavailableError, match="not found on PATH"):
        NodeRefundHarness()
