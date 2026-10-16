"""Target catalog built from a reviewed, synthetic fixture manifest. Never from request bodies."""

from collections.abc import Mapping

from gauntlet.ports import TargetProfile


class StaticTargetCatalog:
    def __init__(self, *profiles: TargetProfile) -> None:
        self._by_id = {profile.target_id: profile for profile in profiles}
        if len(self._by_id) != len(profiles):
            raise ValueError("target IDs must be unique")

    async def get(self, target_id: str) -> TargetProfile | None:
        return self._by_id.get(target_id)


def profile_from_manifest(manifest: Mapping[str, object]) -> TargetProfile:
    """Customers become synthetic actors, assistants become agents, routes become prefixes."""
    if manifest.get("synthetic_only") is not True:
        raise ValueError("only synthetic fixture manifests may define a target")
    target_id, fixture_id = manifest.get("target_id"), manifest.get("fixture_id")
    routes, identities = manifest.get("routes"), manifest.get("identities")
    if not (
        isinstance(target_id, str)
        and isinstance(fixture_id, str)
        and isinstance(routes, list)
        and isinstance(identities, list)
    ):
        raise ValueError("fixture manifest lacks target, fixture, routes or identities")
    paths = tuple(
        r["path"] for r in routes if isinstance(r, dict) and isinstance(r.get("path"), str)
    )
    people = [i for i in identities if isinstance(i, dict) and isinstance(i.get("id"), str)]
    if not paths:
        raise ValueError("fixture manifest declares no routes")
    return TargetProfile(
        target_id=target_id,
        fixture_ids=frozenset({fixture_id}),
        synthetic_actor_ids=frozenset(i["id"] for i in people if i.get("role") == "customer"),
        agent_ids=frozenset(i["id"] for i in people if i.get("role") == "assistant"),
        route_prefixes=paths,
    )
