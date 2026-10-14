"""Read-only repository access for change analysis."""

from typing import Protocol

from gauntlet.contracts import ChangeImpactMap, ChangeRequest, SourceRef


class RepositoryInspector(Protocol):
    async def inspect_change(self, change: ChangeRequest) -> ChangeImpactMap: ...

    async def read_source(self, repository_id: str, ref: SourceRef) -> str:
        """Return the exact lines named by ``ref``. Must refuse secrets, deps and bench paths."""
        ...
