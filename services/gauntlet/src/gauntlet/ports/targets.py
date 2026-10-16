"""Server-side registry of authorized test targets and their synthetic identities."""

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import unquote


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
        """Prefix match on the *decoded* path. Anything that could resolve elsewhere after
        URL normalisation (dot segments, encoded separators, double encoding) is refused."""
        raw = path.split("?", 1)[0].split("#", 1)[0]
        route = unquote(raw)
        if (
            not route.startswith("/")
            or route.startswith("//")
            or "\\" in route
            or "%" in route
            or any(segment in (".", "..") for segment in route.split("/"))
        ):
            return False
        return any(
            prefix == "/" or route == prefix or route.startswith(prefix.rstrip("/") + "/")
            for prefix in self.route_prefixes
        )


class TargetCatalog(Protocol):
    async def get(self, target_id: str) -> TargetProfile | None:
        """Return None for unknown targets; callers must then refuse to plan or execute."""
        ...
