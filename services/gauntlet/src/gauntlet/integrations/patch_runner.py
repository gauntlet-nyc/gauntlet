"""Apply an approved fix plan in a fresh, isolated Git worktree and commit it locally.

Fixed git argv only; the diff is passed on stdin to ``git apply``. Paths are checked against
the plan allowlist before and after applying. The commit stays in the local fixture
repository so the sandbox can export it; nothing is pushed anywhere.
"""

import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Final

from gauntlet.application.gate.repair import PatchedRevision, diff_paths
from gauntlet.contracts import FixPlan
from gauntlet.domain import is_patch_path_allowed
from gauntlet.ports.errors import EnvironmentUnavailableError

_IDENTITY: Final = {
    "GIT_AUTHOR_NAME": "Gauntlet Patch Runner",
    "GIT_AUTHOR_EMAIL": "patch-runner@example.invalid",
    "GIT_COMMITTER_NAME": "Gauntlet Patch Runner",
    "GIT_COMMITTER_EMAIL": "patch-runner@example.invalid",
    "GIT_AUTHOR_DATE": "2026-10-16T12:00:00+00:00",
    "GIT_COMMITTER_DATE": "2026-10-16T12:00:00+00:00",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}


class GitWorktreePatchRunner:
    label = "local_git_worktree"

    def __init__(self, repository: Path) -> None:
        self._repo = repository

    def _git(self, cwd: Path, *args: str, stdin: bytes | None = None) -> str:
        return self._git_raw(cwd, *args, stdin=stdin).strip()

    def _git_raw(self, cwd: Path, *args: str, stdin: bytes | None = None) -> str:
        done = subprocess.run(
            ["git", *args],
            cwd=cwd,
            input=stdin,
            capture_output=True,
            timeout=60,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), **_IDENTITY},
        )
        if done.returncode != 0:
            raise EnvironmentUnavailableError(f"git {args[0]} failed")
        return done.stdout.decode()

    def _apply(self, base_sha: str, plan: FixPlan) -> PatchedRevision:
        declared = diff_paths(plan.unified_diff)
        if any(p not in plan.allowed_paths or not is_patch_path_allowed(p) for p in declared):
            raise ValueError("diff names a path outside the approved allowlist")
        tree = Path(tempfile.mkdtemp(prefix="gauntlet-patch-")) / "tree"
        try:
            self._git(self._repo, "worktree", "add", "--detach", "-q", str(tree), base_sha)
            diff = plan.unified_diff.encode()
            self._git(tree, "apply", "--check", "--whitespace=nowarn", "-", stdin=diff)
            self._git(tree, "apply", "--whitespace=nowarn", "-", stdin=diff)
            status = self._git_raw(tree, "status", "--porcelain=v1", "-z", "--untracked-files=all")
            changed = tuple(entry[3:] for entry in status.split("\0") if entry)
            if not changed or set(changed) - set(declared):
                raise ValueError("applied patch changed undeclared files")
            self._git(tree, "add", "--", *changed)
            self._git(tree, "commit", "-q", "-m", f"Gauntlet fix plan {plan.fix_plan_id}")
            return PatchedRevision(self._git(tree, "rev-parse", "HEAD"), changed)
        finally:
            try:
                self._git(self._repo, "worktree", "remove", "--force", str(tree))
            except EnvironmentUnavailableError:
                shutil.rmtree(tree, ignore_errors=True)

    async def apply(self, *, base_sha: str, plan: FixPlan) -> PatchedRevision:
        return await asyncio.to_thread(self._apply, base_sha, plan)
