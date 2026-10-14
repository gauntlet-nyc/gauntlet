"""A-09: changed components are traced to the routes that render them."""

import asyncio
import subprocess
from pathlib import Path

import pytest
from gauntlet.analysis import (
    GitLimits,
    GitRepositoryInspector,
    build_import_graph,
    routes_rendering,
)
from gauntlet.contracts import ChangeImpactMap, ChangeRequest

FILES = {
    "src/app/layout.tsx": (
        'import "./globals.css";\nimport { FloatingHelp } from "../components/FloatingHelp";\n'
    ),
    "src/app/checkout/page.tsx": 'import { CheckoutButton } from "@/components/CheckoutButton";\n',
    "src/app/products/[id]/page.tsx": (
        'import Card from "../../../components/cards";\nimport React from "react";\n'
    ),
    "src/components/FloatingHelp.tsx": "export function FloatingHelp() {}\n",
    "src/components/CheckoutButton.tsx": 'export { Spinner } from "./ui/Spinner";\n',
    "src/components/ui/Spinner.tsx": "export function Spinner() {}\n",
    "src/components/cards/index.ts": (
        'const Price = require("./Price");\nconst lazy = import("./Lazy");\n'
    ),
    "src/components/cards/Price.js": "module.exports = 1;\n",
    "src/components/cards/Lazy.tsx": "export default 1;\n",
    "src/lib/broken.ts": (
        'import x from "./does-not-exist";\nimport y from "../../../../outside";\n'
    ),
}
ALIASES = {"@/": "src/"}


def test_graph_resolves_relative_alias_index_require_and_dynamic_imports() -> None:
    graph = build_import_graph(FILES, ALIASES)
    assert graph.imports["src/app/checkout/page.tsx"] == {"src/components/CheckoutButton.tsx"}
    assert graph.imports["src/app/products/[id]/page.tsx"] == {"src/components/cards/index.ts"}
    assert graph.imports["src/components/cards/index.ts"] == {
        "src/components/cards/Price.js",
        "src/components/cards/Lazy.tsx",
    }
    assert graph.imports["src/components/CheckoutButton.tsx"] == {"src/components/ui/Spinner.tsx"}


def test_packages_and_assets_are_ignored_but_broken_relative_imports_are_gaps() -> None:
    graph = build_import_graph(FILES, ALIASES)
    assert ("src/app/layout.tsx", "./globals.css") not in graph.unresolved
    assert not any(spec == "react" for _, spec in graph.unresolved)
    assert graph.unresolved == {
        ("src/lib/broken.ts", "./does-not-exist"),
        ("src/lib/broken.ts", "../../../../outside"),
    }


@pytest.mark.parametrize(
    ("changed", "routes"),
    [
        ("src/components/FloatingHelp.tsx", ("src/app/layout.tsx",)),
        ("src/components/ui/Spinner.tsx", ("src/app/checkout/page.tsx",)),
        ("src/components/cards/Price.js", ("src/app/products/[id]/page.tsx",)),
        ("src/lib/broken.ts", ()),
    ],
)
def test_routes_rendering_follows_transitive_imports(changed: str, routes: tuple[str, ...]) -> None:
    assert routes_rendering(build_import_graph(FILES, ALIASES), changed) == routes


def test_depth_limit_bounds_the_search() -> None:
    graph = build_import_graph(FILES, ALIASES)
    assert routes_rendering(graph, "src/components/ui/Spinner.tsx", max_depth=1) == ()


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
         "-c", "commit.gpgsign=false", *args],
        check=True, capture_output=True, text=True,
    ).stdout.strip()  # fmt: skip


def _repo_with_change(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "shop"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    for rel, text in FILES.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "src/components/ui/Spinner.tsx").write_text(
        'export function Spinner() { return <div className="fixed bottom-0 z-50" />; }\n',
        encoding="utf-8",
    )
    _git(repo, "commit", "-q", "-am", "make spinner fixed")
    return repo, base, _git(repo, "rev-parse", "HEAD")


def _inspect(repo: Path, base: str, head: str, limits: GitLimits | None = None) -> ChangeImpactMap:
    inspector = GitRepositoryInspector({"shop": repo}, limits=limits, import_aliases=ALIASES)
    change = ChangeRequest(
        repository_id="shop", base_sha=base, head_sha=head, fixture_id="f", target_id="t",
        max_cost_usd_cents=100,
    )  # fmt: skip
    return asyncio.run(inspector.inspect_change(change))


def test_inspector_adds_rendering_route_with_changed_line_citations(tmp_path: Path) -> None:
    repo, base, head = _repo_with_change(tmp_path)
    impact = _inspect(repo, base, head)
    route = next(s for s in impact.surfaces if s.kind == "route")
    assert route.identifier == "/checkout"
    assert route.confidence == 0.6
    assert route.source_refs[0].path == "src/components/ui/Spinner.tsx"
    assert any("could not be resolved" in g for g in impact.coverage_gaps)


def test_scan_is_skipped_with_a_gap_when_repository_is_too_large(tmp_path: Path) -> None:
    repo, base, head = _repo_with_change(tmp_path)
    impact = _inspect(repo, base, head, limits=GitLimits(max_scan_files=3))
    assert not any(s.kind == "route" for s in impact.surfaces)
    assert any("Dependency scan skipped" in g for g in impact.coverage_gaps)
