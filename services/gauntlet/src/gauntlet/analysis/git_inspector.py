"""Read-only `RepositoryInspector` over local Git checkouts.

Only fixed git subcommands run, via exec (no shell). Repository-controlled config that can
execute programs (external diff, textconv, fsmonitor, hooks) is disabled per invocation, and
user/system git config is ignored.
"""

import asyncio
import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from gauntlet.contracts import ChangeImpactMap, ChangeRequest, SourceRef
from gauntlet.domain import is_path_allowed

from .diff_parser import ParsedDiff, parse_unified_diff
from .errors import (
    GitCommandError,
    PathNotAllowedError,
    RepositoryNotRegisteredError,
    SourceLimitExceededError,
)
from .surface_mapper import DEFAULT_RULES, SurfaceRule, map_surfaces


@dataclass(frozen=True)
class GitLimits:
    timeout_seconds: float = 20.0
    max_diff_bytes: int = 2_000_000
    max_changed_files: int = 500
    max_source_bytes: int = 1_000_000
    max_read_lines: int = 400


_SAFE_CONFIG: tuple[str, ...] = (
    "-c", "core.fsmonitor=false",
    "-c", f"core.hooksPath={os.devnull}",
    "-c", "core.quotePath=true",
    "-c", "diff.noprefix=false",
    "-c", "diff.mnemonicPrefix=false",
)  # fmt: skip

_DIFF_ARGS: tuple[str, ...] = (
    "diff", "--no-color", "--no-ext-diff", "--no-textconv", "--unified=0",
    "--find-renames", "--src-prefix=a/", "--dst-prefix=b/",
)  # fmt: skip


class GitRepositoryInspector:
    def __init__(
        self,
        repositories: Mapping[str, Path],
        limits: GitLimits | None = None,
        git_executable: str | None = None,
        rules: tuple[SurfaceRule, ...] = DEFAULT_RULES,
    ) -> None:
        resolved = git_executable or shutil.which("git")
        if resolved is None:
            raise GitCommandError("git executable not found")
        self._git = resolved
        self._repositories = dict(repositories)
        self._limits = limits or GitLimits()
        self._rules = rules
        self._env = {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "HOME": os.devnull,
            "LC_ALL": "C",
        }

    async def inspect_change(self, change: ChangeRequest) -> ChangeImpactMap:
        repo = self._repo(change.repository_id)
        base = await self._resolve_commit(repo, change.base_sha)
        head = await self._resolve_commit(repo, change.head_sha)
        raw = await self._run(repo, (*_DIFF_ARGS, base, head, "--"), self._limits.max_diff_bytes)
        parsed = parse_unified_diff(raw.decode("utf-8", errors="replace"))
        gaps: list[str] = []
        files = parsed.files
        if len(files) > self._limits.max_changed_files:
            gaps.append(
                f"Only the first {self._limits.max_changed_files} of {len(files)} files analysed"
            )
            files = files[: self._limits.max_changed_files]
        mapping = map_surfaces(
            ParsedDiff(files=files, unparsed_sections=parsed.unparsed_sections),
            base_sha=base,
            head_sha=head,
            rules=self._rules,
        )
        return ChangeImpactMap(
            base_sha=base,
            head_sha=head,
            changed_files=tuple(f.path for f in files if is_path_allowed(f.path)),
            surfaces=mapping.surfaces,
            coverage_gaps=(*gaps, *mapping.coverage_gaps),
        )

    async def read_source(self, repository_id: str, ref: SourceRef) -> str:
        if not is_path_allowed(ref.path):
            raise PathNotAllowedError("path is not readable by analysis")
        if ref.end_line - ref.start_line + 1 > self._limits.max_read_lines:
            raise SourceLimitExceededError("requested line range is too large")
        repo = self._repo(repository_id)
        sha = await self._resolve_commit(repo, ref.sha)
        blob = await self._run(repo, ("show", f"{sha}:{ref.path}"), self._limits.max_source_bytes)
        lines = blob.decode("utf-8", errors="replace").splitlines()
        if ref.start_line > len(lines):
            raise GitCommandError("requested lines are beyond the end of the file")
        return "\n".join(lines[ref.start_line - 1 : ref.end_line])

    def _repo(self, repository_id: str) -> Path:
        repo = self._repositories.get(repository_id)
        if repo is None:
            raise RepositoryNotRegisteredError("repository is not registered for analysis")
        return repo

    async def _resolve_commit(self, repo: Path, sha: str) -> str:
        out = await self._run(repo, ("rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}"), 128)
        return out.decode("ascii").strip()

    async def _run(self, repo: Path, args: tuple[str, ...], max_bytes: int) -> bytes:
        process = await asyncio.create_subprocess_exec(
            self._git, "-C", str(repo), *_SAFE_CONFIG, *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._env,
        )  # fmt: skip
        try:
            stdout, _ = await asyncio.wait_for(
                process.communicate(), timeout=self._limits.timeout_seconds
            )
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise GitCommandError(f"git {args[0]} timed out") from exc
        if process.returncode != 0:
            raise GitCommandError(f"git {args[0]} failed with exit code {process.returncode}")
        if len(stdout) > max_bytes:
            raise SourceLimitExceededError(f"git {args[0]} output exceeded {max_bytes} bytes")
        return stdout
