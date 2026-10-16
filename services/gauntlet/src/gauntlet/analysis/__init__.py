"""Read-only change analysis: bounded git access, diff parsing and surface mapping (owner A)."""

from gauntlet.domain import is_path_allowed

from .dependency_graph import ImportGraph, build_import_graph, routes_rendering
from .diff_parser import FileChange, FileStatus, Hunk, ParsedDiff, parse_unified_diff
from .errors import (
    GitCommandError,
    PathNotAllowedError,
    RepositoryNotRegisteredError,
    SourceLimitExceededError,
)
from .git_inspector import GitLimits, GitRepositoryInspector
from .signals import extract_signals
from .surface_mapper import DEFAULT_RULES, SurfaceMapping, SurfaceRule, map_surfaces

__all__ = [
    "DEFAULT_RULES",
    "FileChange",
    "FileStatus",
    "GitCommandError",
    "GitLimits",
    "GitRepositoryInspector",
    "Hunk",
    "ImportGraph",
    "ParsedDiff",
    "PathNotAllowedError",
    "RepositoryNotRegisteredError",
    "SourceLimitExceededError",
    "SurfaceMapping",
    "SurfaceRule",
    "build_import_graph",
    "extract_signals",
    "is_path_allowed",
    "map_surfaces",
    "parse_unified_diff",
    "routes_rendering",
]
