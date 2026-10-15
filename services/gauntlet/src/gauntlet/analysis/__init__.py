"""Read-only change analysis: bounded git access, diff parsing and surface mapping (owner A)."""

from .diff_parser import FileChange, FileStatus, Hunk, ParsedDiff, parse_unified_diff
from .errors import (
    GitCommandError,
    PathNotAllowedError,
    RepositoryNotRegisteredError,
    SourceLimitExceededError,
)
from .git_inspector import GitLimits, GitRepositoryInspector
from .path_policy import is_path_allowed
from .surface_mapper import DEFAULT_RULES, SurfaceMapping, SurfaceRule, map_surfaces

__all__ = [
    "DEFAULT_RULES",
    "FileChange",
    "FileStatus",
    "GitCommandError",
    "GitLimits",
    "GitRepositoryInspector",
    "Hunk",
    "ParsedDiff",
    "PathNotAllowedError",
    "RepositoryNotRegisteredError",
    "SourceLimitExceededError",
    "SurfaceMapping",
    "SurfaceRule",
    "is_path_allowed",
    "map_surfaces",
    "parse_unified_diff",
]
