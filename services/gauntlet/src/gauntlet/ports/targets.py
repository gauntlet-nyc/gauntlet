"""Server-side registry of authorized test targets and their synthetic identities."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TargetProfile:
    """Everything an attack may reference on a target. Built from a reviewed manifest, never
    from model output or request bodies."""

    target_id: str
    fixture_ids: frozenset[str]
    synthetic_actor_ids: frozenset[str]
    agent_ids: frozenset[str]
    route_prefixes: tuple[str, ...]

    def allows_route(self, path: str) -> bool:
        route = path.split("?", 1)[0].split("#", 1)[0]
        return any(
            prefix == "/" or route == prefix or route.startswith(prefix.rstrip("/") + "/")
            for prefix in self.route_prefixes
        )


class TargetCatalog(Protocol):
    async def get(self, target_id: str) -> TargetProfile | None:
        """Return None for unknown targets; callers must then refuse to plan or execute."""
        ...
