"""The offline Cartwheel UI proposal is a scoped, applicable change to exact head CSS."""

import asyncio
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from gauntlet.composition import GateTarget, build_gate
from gauntlet.contracts import AttackSpec, Finding
from gauntlet.integrations import fix_proposers
from gauntlet.settings import Settings

ROOT = Path(__file__).resolve().parents[3]
CSS = "src/components/FloatingHelp.module.css"


def git(repo: Path, *args: str, stdin: str | None = None) -> str:
    return subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        input=stdin,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


@pytest.fixture
def ui_case(tmp_path: Path) -> tuple[Path, GateTarget, AttackSpec, Finding]:
    repo = tmp_path / "cartwheel"
    subprocess.run(
        [sys.executable, "scripts/build_cartwheel_fixture.py", "--dest", str(repo)],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    target = GateTarget.cartwheel(repo)

    async def run() -> tuple[AttackSpec, Finding]:
        runtime = await build_gate(
            Settings.from_env({}),
            target,
            model="scripted",
            sandbox="fake",
            browser="fake",
            artifact_root=tmp_path / "ev",
        )
        try:
            report = await runtime.use_case.execute(
                "ui-fix", target.change(), target.fixture_checksum
            )
            return report.outcomes[0].attack, report.outcomes[0].finding
        finally:
            await runtime.aclose()

    attack, finding = asyncio.run(run())
    git(repo, "checkout", "--detach", target.head_sha)
    return repo, target, attack, finding


@pytest.mark.asyncio
async def test_ui_fix_applies_to_exact_head_and_preserves_help(
    ui_case: tuple[Path, GateTarget, AttackSpec, Finding],
) -> None:
    repo, target, attack, finding = ui_case
    # The proposal must read the pinned commit, not an untrusted working-tree edit.
    (repo / CSS).write_text(".unrelated { display: none; }\n")
    proposer = fix_proposers.ScriptedUiFixProposer(repo, datetime.now(UTC))
    plan = await proposer.propose(
        run_id="ui-fix", finding=finding, attack=attack, head_sha=target.head_sha
    )
    assert proposer.label == "offline_scripted_fix"
    assert plan.base_sha == target.head_sha and plan.allowed_paths == (CSS,)
    assert (repo / CSS).read_text() == ".unrelated { display: none; }\n"
    git(repo, "restore", "--", CSS)
    git(repo, "apply", "--check", "-", stdin=plan.unified_diff)
    git(repo, "apply", "-", stdin=plan.unified_diff)
    assert git(repo, "diff", "--name-only") == CSS
    assert (repo / CSS).read_text() == (
        ".floatingHelp {\n  position: fixed;\n  bottom: 96px;\n  right: 16px;\n  z-index: 50;\n}\n"
    )
    assert git(repo, "diff", "--", "src/components/FloatingHelp.tsx", "tests") == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["path", "sha", "target", "fixture", "source"])
async def test_ui_fix_refuses_unrelated_or_uncited_source(
    ui_case: tuple[Path, GateTarget, AttackSpec, Finding],
    mutation: str,
) -> None:
    repo, target, attack, finding = ui_case
    head = target.head_sha
    if mutation in {"path", "sha"}:
        refs = tuple(
            ref.model_copy(
                update={mutation: "tests/protected.css" if mutation == "path" else "a" * 40}
            )
            for ref in attack.source_refs
        )
        attack = attack.model_copy(update={"source_refs": refs})
    elif mutation in {"target", "fixture"}:
        attack = attack.model_copy(update={f"{mutation}_id": "unrelated"})
    else:
        (repo / CSS).write_text(".floatingHelp { display: none; }\n")
        git(repo, "commit", "-am", "unrelated CSS")
        head = git(repo, "rev-parse", "HEAD")
        attack = attack.model_copy(
            update={
                "source_refs": tuple(
                    ref.model_copy(update={"sha": head}) for ref in attack.source_refs
                )
            }
        )
    proposer = fix_proposers.ScriptedUiFixProposer(repo, datetime.now(UTC))
    with pytest.raises(ValueError):
        await proposer.propose(run_id="ui-fix", finding=finding, attack=attack, head_sha=head)
    assert git(repo, "status", "--porcelain") == ""
