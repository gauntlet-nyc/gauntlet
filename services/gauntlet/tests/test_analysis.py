"""Diff parsing, surface mapping and the read-only git inspector against a real repository."""

import asyncio
import subprocess
from pathlib import Path

import pytest
from conftest import DemoRepo

from gauntlet.analysis import (
    FileStatus,
    GitCommandError,
    GitRepositoryInspector,
    PathNotAllowedError,
    RepositoryNotRegisteredError,
    SourceLimitExceededError,
    is_path_allowed,
    map_surfaces,
    parse_unified_diff,
)
from gauntlet.contracts import ChangeImpactMap, ChangeRequest, SourceRef

SAMPLE_DIFF = """diff --git a/web/a.css b/web/a.css
index 1..2 100644
--- a/web/a.css
+++ b/web/a.css
@@ -3,0 +4,2 @@ .x {
+  position: fixed;
+  bottom: 0;
diff --git a/api/src/routes/old.ts b/api/src/routes/old.ts
deleted file mode 100644
--- a/api/src/routes/old.ts
+++ /dev/null
@@ -1,2 +0,0 @@
-router.get("/x", h);
-export {};
diff --git a/img/logo.png b/img/logo.png
new file mode 100644
Binary files /dev/null and b/img/logo.png differ
diff --git a/web/Old.tsx b/web/New.tsx
similarity index 100%
rename from web/Old.tsx
rename to web/New.tsx
diff --git "a/odd\\tname" "b/odd\\tname"
"""


def test_parser_handles_add_delete_binary_rename_and_quoted() -> None:
    parsed = parse_unified_diff(SAMPLE_DIFF)
    by_path = {f.path: f for f in parsed.files}
    css = by_path["web/a.css"]
    assert css.status is FileStatus.MODIFIED
    assert css.hunks[0].new_start == 4 and css.hunks[0].new_count == 2
    assert css.hunks[0].added == ("  position: fixed;", "  bottom: 0;")
    deleted = by_path["api/src/routes/old.ts"]
    assert deleted.status is FileStatus.DELETED and deleted.hunks[0].new_count == 0
    assert by_path["img/logo.png"].binary
    renamed = by_path["web/New.tsx"]
    assert renamed.status is FileStatus.RENAMED and renamed.old_path == "web/Old.tsx"
    assert len(parsed.unparsed_sections) == 1


def test_mapper_cites_changed_lines_and_reports_gaps() -> None:
    mapping = map_surfaces(parse_unified_diff(SAMPLE_DIFF), base_sha="1111111", head_sha="2222222")
    style = next(s for s in mapping.surfaces if s.kind == "style")
    assert style.source_refs[0].sha == "2222222"
    assert (style.source_refs[0].start_line, style.source_refs[0].end_line) == (4, 5)
    api = next(s for s in mapping.surfaces if s.kind == "api")
    assert api.source_refs[0].sha == "1111111", "pure deletions cite the base commit"
    assert any("Binary" in g for g in mapping.coverage_gaps)
    assert any("rename" in g for g in mapping.coverage_gaps)
    assert any("Could not parse" in g for g in mapping.coverage_gaps)


def test_unparsed_diff_header_does_not_reveal_sensitive_filename() -> None:
    diff = 'diff --git "a/.env.secret" "b/.env.secret"\n'
    mapping = map_surfaces(parse_unified_diff(diff), base_sha="1111111", head_sha="2222222")
    assert mapping.coverage_gaps
    assert ".env.secret" not in " ".join(mapping.coverage_gaps)


@pytest.mark.parametrize(
    ("path", "allowed"),
    [
        ("web/src/a.tsx", True),
        (".env", False),
        ("config/.env.local", False),
        ("bench/private/truth.json", False),
        ("node_modules/x/index.js", False),
        ("deploy/server.pem", False),
        ("deploy/server.PEM", False),
        (".ENV", False),
        ("config/.Env.local", False),
        ("Bench/Private/truth.json", False),
        ("BENCH/heldout/x", False),
        (".GIT/config", False),
        ("Node_Modules/x/index.js", False),
        ("Secrets/a.txt", False),
        ("../outside.ts", False),
        ("/etc/passwd", False),
        # Case-insensitive file systems (macOS, Windows): every spelling is the same file.
        (".ENV", False),
        (".Env.local", False),
        ("Bench/Private/truth.json", False),
        ("Secrets/token.txt", False),
        ("src/x.PEM", False),
        (".GIT/config", False),
        ("Node_Modules/x/index.js", False),
    ],
)
def test_path_policy(path: str, allowed: bool) -> None:
    assert is_path_allowed(path) is allowed


def _inspect(repo: DemoRepo, head: str) -> ChangeImpactMap:
    inspector = GitRepositoryInspector({"cartwheel": repo.path})
    change = ChangeRequest(
        repository_id="cartwheel",
        base_sha=repo.base[:8],
        head_sha=head[:8],
        fixture_id="baseline-v1",
        target_id="cartwheel-fixture",
        max_cost_usd_cents=500,
    )
    return asyncio.run(inspector.inspect_change(change))


def test_ui_change_maps_to_component_and_style(demo_repo: DemoRepo) -> None:
    impact = _inspect(demo_repo, demo_repo.ui_head)
    assert impact.head_sha == demo_repo.ui_head, "short SHAs resolve to full commits"
    kinds = {(s.kind, s.identifier) for s in impact.surfaces}
    assert ("component", "FloatingHelp") in kinds
    assert ("style", "web/src/components/FloatingHelp.tsx") in kinds
    assert ".env" not in impact.changed_files
    assert any("sensitive" in gap for gap in impact.coverage_gaps)


def test_tool_change_maps_to_agent_tool_citing_removed_check(demo_repo: DemoRepo) -> None:
    impact = _inspect(demo_repo, demo_repo.tool_head)
    tool = next(s for s in impact.surfaces if s.kind == "agent_tool")
    assert tool.identifier == "request_refund"
    ref = tool.source_refs[0]
    assert ref.sha == demo_repo.base and (ref.start_line, ref.end_line) == (3, 5)


def test_read_source_returns_exact_lines(demo_repo: DemoRepo) -> None:
    inspector = GitRepositoryInspector({"cartwheel": demo_repo.path})
    ref = SourceRef(path="api/src/tools/request_refund.ts", sha=demo_repo.base, start_line=3,
                    end_line=3)  # fmt: skip
    text = asyncio.run(inspector.read_source("cartwheel", ref))
    assert text == "  if (order.ownerId !== ctx.actorId) {"


def test_read_source_refuses_secrets_and_large_ranges(demo_repo: DemoRepo) -> None:
    inspector = GitRepositoryInspector({"cartwheel": demo_repo.path})
    with pytest.raises(PathNotAllowedError):
        asyncio.run(inspector.read_source(
            "cartwheel", SourceRef(path=".env", sha=demo_repo.base, start_line=1, end_line=1)
        ))  # fmt: skip
    with pytest.raises(SourceLimitExceededError):
        asyncio.run(inspector.read_source(
            "cartwheel",
            SourceRef(path="README.md", sha=demo_repo.base, start_line=1, end_line=5000),
        ))  # fmt: skip


def test_unregistered_repo_and_unknown_commit_are_rejected(demo_repo: DemoRepo) -> None:
    inspector = GitRepositoryInspector({"cartwheel": demo_repo.path})
    ref = SourceRef(path="README.md", sha="deadbeef", start_line=1, end_line=1)
    with pytest.raises(RepositoryNotRegisteredError):
        asyncio.run(inspector.read_source("other-repo", ref))
    with pytest.raises(GitCommandError):
        asyncio.run(inspector.read_source("cartwheel", ref))


def test_repository_config_cannot_run_external_diff(demo_repo: DemoRepo, tmp_path: Path) -> None:
    marker = tmp_path / "pwned"
    script = tmp_path / "evil.sh"
    script.write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
    script.chmod(0o755)
    for key, value in (("diff.external", str(script)), ("diff.evil.textconv", str(script))):
        subprocess.run(["git", "-C", str(demo_repo.path), "config", key, value], check=True)
    (demo_repo.path / ".git" / "info" / "attributes").write_text("* diff=evil\n", encoding="utf-8")
    impact = _inspect(demo_repo, demo_repo.ui_head)
    assert impact.surfaces
    assert not marker.exists()


def test_read_source_refuses_mixed_case_secret_paths(demo_repo: DemoRepo) -> None:
    """Regression for B's review on #5: a tracked `.ENV` must never be read for a model."""
    subprocess.run(["git", "-C", str(demo_repo.path), "mv", ".env", ".ENV.tmp"], check=True)
    subprocess.run(["git", "-C", str(demo_repo.path), "mv", ".ENV.tmp", ".ENV"], check=True)
    subprocess.run(
        ["git", "-C", str(demo_repo.path), "-c", "user.name=t", "-c", "user.email=t@x.invalid",
         "commit", "-q", "-m", "rename"],
        check=True,
    )  # fmt: skip
    head = subprocess.run(
        ["git", "-C", str(demo_repo.path), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()  # fmt: skip
    inspector = GitRepositoryInspector({"cartwheel": demo_repo.path})
    with pytest.raises(PathNotAllowedError):
        asyncio.run(inspector.read_source(
            "cartwheel", SourceRef(path=".ENV", sha=head, start_line=1, end_line=1)
        ))  # fmt: skip
