"""P7: confirmed findings become verified memory; later plans read it as of a time."""

import asyncio
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from gauntlet.application.gate.learn import LearnFromGateUseCase
from gauntlet.application.gate.run_gate import GateRunReport
from gauntlet.composition import GateTarget, build_gate
from gauntlet.domain import GateStatus
from gauntlet.integrations.fake.memory import InMemoryTemporalMemory, JsonFileTemporalMemory
from gauntlet.settings import Settings

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, str]]:
    repo = tmp_path_factory.mktemp("mem") / "cartwheel"
    out = subprocess.run(
        [sys.executable, "scripts/build_cartwheel_clean_fixture.py", "--dest", str(repo)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return repo, json.loads(out.stdout)


def gate(
    target: GateTarget, tmp: Path, memory: InMemoryTemporalMemory | None, run_id: str
) -> GateRunReport:
    async def go() -> GateRunReport:
        runtime = await build_gate(
            Settings.from_env({}), target, model="scripted", sandbox="fake", browser="fake",
            artifact_root=tmp / run_id, memory=memory,
        )  # fmt: skip
        try:
            return await runtime.use_case.execute(
                run_id, target.change(intent="x"), target.fixture_checksum
            )
        finally:
            await runtime.aclose()

    return asyncio.run(go())


def test_verified_finding_informs_the_next_plan(
    built: tuple[Path, dict[str, str]], tmp_path: Path
) -> None:
    memory = InMemoryTemporalMemory()
    help_target = GateTarget.cartwheel(built[0])
    first = gate(help_target, tmp_path, memory, "run-1")
    learned = asyncio.run(
        LearnFromGateUseCase(memory, lambda: datetime.now(UTC) - timedelta(seconds=1)).remember(
            first
        )
    )
    (fact,) = learned
    assert fact.verification == "confirmed" and fact.trust == "verified_test"
    assert fact.source.finding_id == first.findings[0].finding_id
    assert fact.source.commit == help_target.head_sha
    assert {"style", "component"} <= set(fact.surface_kinds)

    clean = GateTarget.cartwheel(built[0])
    from dataclasses import replace

    clean = replace(clean, clean_head_sha=built[1]["clean_sha"])
    without = gate(clean, tmp_path, None, "run-2")
    with_memory = gate(clean, tmp_path, memory, "run-3")
    assert len(with_memory.plan.attacks) == len(without.plan.attacks) + 1
    assert with_memory.events[1].payload["memory_fact_ids"] == fact.fact_id
    assert fact.fact_id in with_memory.plan.attacks[-1].why_this_change
    assert with_memory.overall is GateStatus.PASSED


def test_passed_findings_are_not_remembered(
    built: tuple[Path, dict[str, str]], tmp_path: Path
) -> None:
    from dataclasses import replace

    clean = replace(GateTarget.cartwheel(built[0]), clean_head_sha=built[1]["clean_sha"])
    memory = InMemoryTemporalMemory()
    report = gate(clean, tmp_path, None, "run-4")
    assert (
        asyncio.run(LearnFromGateUseCase(memory, lambda: datetime.now(UTC)).remember(report)) == ()
    )


def test_memory_learned_later_is_invisible_to_an_earlier_plan(
    built: tuple[Path, dict[str, str]], tmp_path: Path
) -> None:
    memory = InMemoryTemporalMemory()
    target = GateTarget.cartwheel(built[0])
    report = gate(target, tmp_path, memory, "run-5")
    future = datetime.now(UTC) + timedelta(days=1)
    asyncio.run(LearnFromGateUseCase(memory, lambda: future).remember(report))
    again = gate(target, tmp_path, memory, "run-6")  # plans "now", before the fact was known
    assert again.events[1].payload["memory_fact_ids"] is None
    assert len(again.plan.attacks) == len(report.plan.attacks)


def test_file_memory_is_append_only(tmp_path: Path, built: tuple[Path, dict[str, str]]) -> None:
    memory = JsonFileTemporalMemory(tmp_path / "facts.json")
    report = gate(GateTarget.cartwheel(built[0]), tmp_path, None, "run-7")
    (fact,) = asyncio.run(LearnFromGateUseCase(memory, lambda: datetime.now(UTC)).remember(report))
    reloaded = JsonFileTemporalMemory(tmp_path / "facts.json")
    assert [f.fact_id for f in reloaded.all()] == [fact.fact_id]
    from gauntlet.ports import PortError

    with pytest.raises(PortError):
        asyncio.run(reloaded.remember(fact))
