"""Exercise local repair export/build/server lifecycle with real bounded processes."""

import asyncio
import subprocess
from pathlib import Path

import pytest

from gauntlet.integrations.ui_repair_sandbox import LocalUIRepairSandbox
from gauntlet.ports.errors import EnvironmentUnavailableError

CSS = "src/components/FloatingHelp.module.css"


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


@pytest.fixture
def setup(tmp_path: Path) -> tuple[Path, Path, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.invalid")
    for name in (
        "package.json",
        "next.config.js",
        "src/app/checkout/page.tsx",
        "src/app/api/build-info/route.ts",
        CSS,
    ):
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("initial")
    (repo / ".gitignore").write_text("node_modules/\n.next/\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "head")
    head = git(repo, "rev-parse", "HEAD")
    (repo / CSS).write_text("patched")
    git(repo, "commit", "-qam", "approved CSS")
    patch = git(repo, "rev-parse", "HEAD")
    cache = tmp_path / "node_modules"
    runner = cache / "next/dist/bin/next"
    runner.parent.mkdir(parents=True)
    runner.write_text("""
const fs = require('fs');
const cp = require('child_process');
if (process.env.AWS_SECRET_ACCESS_KEY || process.env.ANCHOR_API_KEY) process.exit(7);
if (process.argv[2] === 'build') {
 fs.mkdirSync('.next');
 fs.writeFileSync('.next/sha', cp.execFileSync('git',['rev-parse','HEAD']).toString().trim());
} else {
 const sha = fs.readFileSync('.next/sha','utf8');
 const port = Number(process.argv[process.argv.indexOf('-p') + 1]);
 require('http').createServer((req,res) => {
  res.setHeader('Content-Type','application/json');
  res.end(JSON.stringify({schema_version:'1.0',source_sha:sha}));
 }).listen(port,'127.0.0.1');
}
""")
    return repo, cache, head, patch


def sandbox(setup: tuple[Path, Path, str, str], **kwargs: object) -> LocalUIRepairSandbox:
    repo, cache, head, _ = setup
    return LocalUIRepairSandbox(
        repo,
        target_id="cartwheel-fixture",
        fixture_id="baseline-v1",
        fixture_checksum="c" * 64,
        head_sha=head,
        dependency_cache=cache,
        **kwargs,
    )


def test_actual_export_build_receipt_and_cleanup(
    setup: tuple[Path, Path, str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "must-not-reach-child")
    monkeypatch.setenv("ANCHOR_API_KEY", "must-not-reach-child")
    provider = sandbox(setup)
    provider.allow(setup[3])

    async def run() -> None:
        env = await provider.create(
            target_id="cartwheel-fixture",
            source_sha=setup[3],
            fixture_id="baseline-v1",
            mode="fix_regression",
        )
        root = provider.root_of(env.environment_id)
        assert root != setup[0]
        assert (root / CSS).read_text() == "patched"
        assert env.source_sha == setup[3]
        assert env.preview_origin.startswith("http://127.0.0.1:")
        assert await provider.verify_fixture(env.environment_id, "c" * 64)
        assert not await provider.verify_fixture(env.environment_id, "d" * 64)
        await provider.destroy(env.environment_id)
        await provider.destroy(env.environment_id)
        assert not root.exists()
        assert not await provider.verify_fixture(env.environment_id, "c" * 64)

    asyncio.run(run())


def test_unregistered_revision_and_non_css_patch_rejected(
    setup: tuple[Path, Path, str, str],
) -> None:
    provider = sandbox(setup)

    async def run() -> None:
        with pytest.raises(EnvironmentUnavailableError):
            await provider.create(
                target_id="cartwheel-fixture",
                source_sha=setup[3],
                fixture_id="baseline-v1",
                mode="fix_regression",
            )

    asyncio.run(run())
    (setup[0] / "package.json").write_text("{}")
    git(setup[0], "add", ".")
    git(setup[0], "commit", "-qm", "unsafe config edit")
    with pytest.raises(EnvironmentUnavailableError):
        provider.allow(git(setup[0], "rev-parse", "HEAD"))


def test_build_timeout_cleans_export(setup: tuple[Path, Path, str, str]) -> None:
    (setup[1] / "next/dist/bin/next").write_text("setInterval(() => {}, 1000);")
    provider = sandbox(setup, build_timeout_seconds=0.1)

    async def run() -> None:
        with pytest.raises(EnvironmentUnavailableError):
            await provider.create(
                target_id="cartwheel-fixture",
                source_sha=setup[2],
                fixture_id="baseline-v1",
                mode="fix_regression",
            )
        assert provider.active_environment_ids == ()

    asyncio.run(run())


@pytest.mark.parametrize("repeat_cancel", [False, True])
def test_cancel_build_kills_process_and_removes_export(
    setup: tuple[Path, Path, str, str],
    tmp_path: Path,
    repeat_cancel: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json
    import os

    marker = tmp_path / "started.json"
    (setup[1] / "next/dist/bin/next").write_text(
        "require('fs').writeFileSync("
        + json.dumps(str(marker))
        + ",JSON.stringify({root:process.cwd(),pid:process.pid}));setInterval(()=>{},1000);"
    )
    provider = sandbox(setup)

    async def run() -> None:
        task = asyncio.create_task(
            provider.create(
                target_id="cartwheel-fixture",
                source_sha=setup[2],
                fixture_id="baseline-v1",
                mode="fix_regression",
            )
        )
        async with asyncio.timeout(10):
            while not marker.exists():
                await asyncio.sleep(0.01)
        details = json.loads(marker.read_text())
        cleanup_started = asyncio.Event()
        release_cleanup = asyncio.Event()
        original_stop = provider._stop

        async def slow_stop(process: asyncio.subprocess.Process) -> None:
            if process.pid == details["pid"]:
                cleanup_started.set()
                await release_cleanup.wait()
            await original_stop(process)

        if repeat_cancel:
            monkeypatch.setattr(provider, "_stop", slow_stop)
        task.cancel()
        if repeat_cancel:
            await asyncio.wait_for(cleanup_started.wait(), 2)
            task.cancel()
            release_cleanup.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not Path(details["root"]).exists()
        with pytest.raises(ProcessLookupError):
            os.kill(details["pid"], 0)
        assert provider.active_environment_ids == ()

    asyncio.run(run())


def test_wrong_build_receipt_never_returns_environment(setup: tuple[Path, Path, str, str]) -> None:
    runner = setup[1] / "next/dist/bin/next"
    runner.write_text(runner.read_text().replace("source_sha:sha", "source_sha:'" + "d" * 40 + "'"))
    provider = sandbox(setup, startup_timeout_seconds=0.3)

    async def run() -> None:
        with pytest.raises(EnvironmentUnavailableError):
            await provider.create(
                target_id="cartwheel-fixture",
                source_sha=setup[2],
                fixture_id="baseline-v1",
                mode="fix_regression",
            )
        assert provider.active_environment_ids == ()

    asyncio.run(run())


def test_missing_dependency_cache_is_explicit_environment_error(
    setup: tuple[Path, Path, str, str], tmp_path: Path
) -> None:
    with pytest.raises(EnvironmentUnavailableError, match="repository or dependency cache"):
        LocalUIRepairSandbox(
            setup[0],
            target_id="cartwheel-fixture",
            fixture_id="baseline-v1",
            fixture_checksum="c" * 64,
            head_sha=setup[2],
            dependency_cache=tmp_path / "missing",
        )


def test_real_cartwheel_ui_fixture_has_no_refund_tool_requirement(
    setup: tuple[Path, Path, str, str], tmp_path: Path
) -> None:
    import runpy

    project = Path(__file__).resolve().parents[3]
    builder = runpy.run_path(str(project / "scripts/build_cartwheel_fixture.py"))
    repository = tmp_path / "actual-cartwheel"
    identity = builder["build"](repository)
    assert not (repository / "api/src/tools/request_refund.ts").exists()
    provider = LocalUIRepairSandbox(
        repository,
        target_id="cartwheel-fixture",
        fixture_id="baseline-v1",
        fixture_checksum=identity["fixture_checksum_sha256"],
        head_sha=identity["head_sha"],
        dependency_cache=setup[1],
    )

    async def run() -> None:
        env = await provider.create(
            target_id="cartwheel-fixture",
            source_sha=identity["head_sha"],
            fixture_id="baseline-v1",
            mode="fix_regression",
        )
        try:
            assert await provider.verify_fixture(
                env.environment_id, identity["fixture_checksum_sha256"]
            )
        finally:
            await provider.destroy(env.environment_id)

    asyncio.run(run())
