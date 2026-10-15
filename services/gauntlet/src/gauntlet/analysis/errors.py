"""Typed failures of the read-only repository adapter."""

from gauntlet.ports import PortError


class RepositoryNotRegisteredError(PortError):
    """The repository ID is not in the server-side allowlist."""


class GitCommandError(PortError):
    """A bounded git invocation failed, timed out, or referenced a missing commit."""


class PathNotAllowedError(PortError):
    """The requested path is outside what analysis may read (secrets, deps, benchmark truth)."""


class SourceLimitExceededError(PortError):
    """A diff or source read exceeded its configured size bound."""
