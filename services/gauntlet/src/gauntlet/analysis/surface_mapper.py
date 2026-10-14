"""Deterministic change-to-surface mapping with line-level citations. Pure; no model involved."""

import hashlib
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Final

from gauntlet.contracts import AffectedSurface, SourceRef
from gauntlet.contracts.gate import SurfaceKind
from gauntlet.domain import is_path_allowed

from .diff_parser import FileChange, FileStatus, Hunk, ParsedDiff
from .signals import extract_signals


@dataclass(frozen=True)
class SurfaceRule:
    kind: SurfaceKind
    path_pattern: re.Pattern[str] | None
    content_pattern: re.Pattern[str] | None
    confidence: float

    def matches(self, path: str, changed_text: str) -> bool:
        if self.path_pattern is not None and not self.path_pattern.search(path):
            return False
        if self.content_pattern is not None and not self.content_pattern.search(changed_text):
            return False
        return True


def _rule(
    kind: SurfaceKind, path: str | None, content: str | None, confidence: float
) -> SurfaceRule:
    return SurfaceRule(
        kind=kind,
        path_pattern=re.compile(path) if path else None,
        content_pattern=re.compile(content, re.IGNORECASE) if content else None,
        confidence=confidence,
    )


_SOURCE = r"\.(tsx?|jsx?|mjs|cjs|py)$"

DEFAULT_RULES: Final[tuple[SurfaceRule, ...]] = (
    _rule("style", r"\.(css|scss|sass|less)$", None, 0.9),
    _rule(
        "style",
        r"\.(tsx|jsx|html|vue|svelte)$",
        r"position:\s*(fixed|sticky|absolute)|z-?index|\b(fixed|sticky)\b[^\n]*\b(top|bottom|left|right|inset)-",
        0.75,
    ),
    _rule("route", r"(^|/)app/(.+/)?(page|layout)\.(tsx|jsx)$", None, 0.85),
    _rule("route", r"(^|/)pages/.+\.(tsx|jsx)$", None, 0.8),
    _rule("component", r"(^|/)components/.+\.(tsx|jsx|vue|svelte)$", None, 0.8),
    _rule("agent_tool", r"(^|/)(tools|assistant|agents?)/.+" + _SOURCE, None, 0.85),
    _rule("agent_tool", _SOURCE, r"\b(input_?schema|tool_choice|tools\s*:|tool_use)\b", 0.6),
    _rule("api", r"(^|/)(routes|api|handlers|controllers)/.+" + _SOURCE, None, 0.8),
    _rule("api", _SOURCE, r"\b(router|app)\.(get|post|put|patch|delete)\s*\(", 0.7),
    _rule("workflow", r"(^|/)(workflows?|checkout|forms?)/.+" + _SOURCE, None, 0.6),
)


def _hash_lines(lines: tuple[str, ...]) -> str:
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _hunk_ref(path: str, hunk: Hunk, base_sha: str, head_sha: str) -> SourceRef:
    if hunk.new_count > 0:
        return SourceRef(
            path=path,
            sha=head_sha,
            start_line=hunk.new_start,
            end_line=hunk.new_start + hunk.new_count - 1,
            content_hash=_hash_lines(hunk.added),
        )
    return SourceRef(
        path=path,
        sha=base_sha,
        start_line=max(hunk.old_start, 1),
        end_line=max(hunk.old_start + hunk.old_count - 1, 1),
        content_hash=_hash_lines(hunk.removed),
    )


def _identifier(kind: SurfaceKind, path: str) -> str:
    if kind == "route":
        parts = PurePosixPath(path).parts
        anchor = "app" if "app" in parts else "pages"
        tail = [p for p in parts[parts.index(anchor) + 1 : -1] if not p.startswith("(")]
        if anchor == "pages":
            tail = [*tail, PurePosixPath(path).stem]
        return "/" + "/".join(p for p in tail if p != "index")
    if kind in ("component", "agent_tool"):
        return PurePosixPath(path).stem
    return path


@dataclass(frozen=True)
class SurfaceMapping:
    surfaces: tuple[AffectedSurface, ...]
    coverage_gaps: tuple[str, ...]


def map_surfaces(
    diff: ParsedDiff,
    base_sha: str,
    head_sha: str,
    rules: tuple[SurfaceRule, ...] = DEFAULT_RULES,
) -> SurfaceMapping:
    surfaces: list[AffectedSurface] = []
    gaps: list[str] = [f"Could not parse diff section: {h}" for h in diff.unparsed_sections]
    for change in diff.files:
        gap = _file_gap(change)
        if gap is not None:
            gaps.append(gap)
            continue
        refs = tuple(_hunk_ref(change.path, h, base_sha, head_sha) for h in change.hunks)
        changed_text = "\n".join(line for h in change.hunks for line in (*h.added, *h.removed))
        best: dict[SurfaceKind, float] = {}
        for rule in rules:
            if rule.matches(change.path, changed_text):
                best[rule.kind] = max(best.get(rule.kind, 0.0), rule.confidence)
        if not best:
            gaps.append(f"No surface rule matched {change.path}")
            continue
        signals = extract_signals(change.path, change.hunks, base_sha, head_sha)
        surfaces.extend(
            AffectedSurface(
                kind=kind,
                identifier=_identifier(kind, change.path),
                source_refs=refs,
                confidence=confidence,
                signals=signals,
            )
            for kind, confidence in sorted(best.items())
        )
    return SurfaceMapping(surfaces=tuple(surfaces), coverage_gaps=tuple(gaps))


def _file_gap(change: FileChange) -> str | None:
    if not is_path_allowed(change.path) or (
        change.old_path is not None and not is_path_allowed(change.old_path)
    ):
        return "Excluded a sensitive or disallowed path from analysis"
    if change.binary:
        return f"Binary change not analysed: {change.path}"
    if not change.hunks:
        if change.status is FileStatus.RENAMED:
            return f"Pure rename not analysed: {change.old_path} -> {change.path}"
        return f"No line changes recorded for {change.path}"
    return None
