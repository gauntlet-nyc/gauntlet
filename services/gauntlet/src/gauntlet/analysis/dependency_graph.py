"""Bounded JS/TS import graph: which routes (pages/layouts) transitively render a changed file.

Regex over import/export/require specifiers, resolving only relative and configured alias
paths. Package imports are ignored. Heuristic by design: an unresolved import is a gap, and
the result only suggests routes to test; it never proves a route is affected.
"""

import re
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Final

SOURCE_SUFFIXES: Final = (".tsx", ".ts", ".jsx", ".js", ".mjs", ".cjs")
_SPECIFIER = re.compile(
    r"""(?:\bimport\s+(?:[^'";]*?\sfrom\s+)?|\bexport\s+[^'";]*?\sfrom\s+|\bimport\s*\(\s*|\brequire\s*\(\s*)['"]([^'"]+)['"]"""
)
_ROUTE_FILE = re.compile(r"(^|/)(app/(.+/)?(page|layout)|pages/.+)\.(tsx|jsx|ts|js)$")


def is_route_file(path: str) -> bool:
    return bool(_ROUTE_FILE.search(path))


def _normalise(parts: list[str]) -> str | None:
    out: list[str] = []
    for part in parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not out:
                return None
            out.pop()
        else:
            out.append(part)
    return "/".join(out)


def _candidates(base: str) -> tuple[str, ...]:
    with_ext = tuple(base + s for s in SOURCE_SUFFIXES)
    index = tuple(f"{base}/index{s}" for s in SOURCE_SUFFIXES)
    return (base, *with_ext, *index)


@dataclass(frozen=True)
class ImportGraph:
    imports: Mapping[str, frozenset[str]]
    unresolved: frozenset[tuple[str, str]] = field(default_factory=frozenset)

    def importers(self) -> dict[str, set[str]]:
        reverse: dict[str, set[str]] = {}
        for source, targets in self.imports.items():
            for target in targets:
                reverse.setdefault(target, set()).add(source)
        return reverse


def build_import_graph(
    files: Mapping[str, str], aliases: Mapping[str, str] | None = None
) -> ImportGraph:
    """`files` maps repo-relative path → source text. `aliases` maps e.g. '@/' → 'src/'."""
    known = set(files)
    alias_map = dict(aliases or {})
    imports: dict[str, frozenset[str]] = {}
    unresolved: set[tuple[str, str]] = set()
    for path, text in files.items():
        resolved: set[str] = set()
        for spec in _SPECIFIER.findall(text):
            suffix = PurePosixPath(spec).suffix
            if suffix and suffix not in SOURCE_SUFFIXES:
                continue  # stylesheet, image, JSON: not part of the render graph
            if spec.startswith("."):
                base = _normalise([*PurePosixPath(path).parent.parts, *spec.split("/")])
            else:
                prefix = next((a for a in alias_map if spec.startswith(a)), None)
                if prefix is None:
                    continue  # package import
                base = _normalise([*alias_map[prefix].split("/"), *spec[len(prefix) :].split("/")])
            target = (
                None if base is None else next((c for c in _candidates(base) if c in known), None)
            )
            if target is None:
                unresolved.add((path, spec))
            else:
                resolved.add(target)
        imports[path] = frozenset(resolved)
    return ImportGraph(imports=imports, unresolved=frozenset(unresolved))


def routes_rendering(graph: ImportGraph, changed: str, max_depth: int = 8) -> tuple[str, ...]:
    """Route files that import `changed` directly or transitively, nearest first."""
    reverse = graph.importers()
    seen = {changed}
    found: list[str] = []
    queue: deque[tuple[str, int]] = deque([(changed, 0)])
    while queue:
        node, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for importer in sorted(reverse.get(node, ())):
            if importer in seen:
                continue
            seen.add(importer)
            if is_route_file(importer):
                found.append(importer)
            queue.append((importer, depth + 1))
    return tuple(found)
