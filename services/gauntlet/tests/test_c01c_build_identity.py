"""The synthetic target must derive its build identity from its own clean repo."""

import importlib.util
import os
import shutil
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]


def builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "build_cartwheel_fixture", ROOT / "scripts/build_cartwheel_fixture.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def checkout(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    repo = tmp_path / "cartwheel"
    refs = builder().build(repo)
    return repo, refs


def load_config(repo: Path, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "node",
            "-e",
            "const config = require('./next.config.js'); "
            "process.stdout.write(config.env.CARTWHEEL_BUILD_SOURCE_SHA)",
        ],
        cwd=repo,
        env={**os.environ, **(env or {})},
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="Node required")
def test_clean_config_derives_full_head_sha(checkout: tuple[Path, dict[str, str]]) -> None:
    repo, refs = checkout
    result = load_config(repo)
    assert result.returncode == 0, result.stderr
    assert result.stdout == refs["head_sha"]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node required")
@pytest.mark.parametrize("dirty_kind", ["tracked", "untracked"])
def test_config_rejects_dirty_source(
    checkout: tuple[Path, dict[str, str]], dirty_kind: str
) -> None:
    repo, _ = checkout
    if dirty_kind == "tracked":
        (repo / "src/app/page.tsx").write_text("// changed after commit\n")
    else:
        (repo / "src/app/extra.tsx").write_text("// untracked source\n")
    result = load_config(repo)
    assert result.returncode != 0
    assert "clean" in result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="Node required")
def test_config_rejects_spoofed_identity_env(checkout: tuple[Path, dict[str, str]]) -> None:
    repo, _ = checkout
    result = load_config(repo, env={"CARTWHEEL_BUILD_SOURCE_SHA": "f" * 40})
    assert result.returncode != 0
    assert "CARTWHEEL_BUILD_SOURCE_SHA" in result.stderr
