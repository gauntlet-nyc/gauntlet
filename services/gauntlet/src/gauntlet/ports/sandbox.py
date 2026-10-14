"""Isolated target environments (Daytona in production, fakes offline)."""

from dataclasses import dataclass
from typing import Protocol

from gauntlet.contracts import ReplayMode


@dataclass(frozen=True)
class EnvironmentHandle:
    environment_id: str
    target_id: str
    source_sha: str
    fixture_id: str
    fixture_checksum: str
    preview_origin: str
    """Exact allowlisted origin a browser may open; never a wildcard."""


class SandboxProvider(Protocol):
    async def create(
        self, *, target_id: str, source_sha: str, fixture_id: str, mode: ReplayMode
    ) -> EnvironmentHandle:
        """Raise EnvironmentUnavailableError on failure; never return a half-ready handle."""
        ...

    async def verify_fixture(self, environment_id: str, expected_checksum: str) -> bool: ...

    async def destroy(self, environment_id: str) -> None:
        """Idempotent: destroying an already-destroyed environment is not an error."""
        ...
