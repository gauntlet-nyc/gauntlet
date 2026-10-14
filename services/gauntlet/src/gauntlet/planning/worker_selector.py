"""Which workers a change may use is decided by its surfaces, not by the model."""

from typing import Final

from gauntlet.contracts import ChangeImpactMap, SurfaceKind, WorkerKind

WORKERS_BY_SURFACE: Final[dict[SurfaceKind, frozenset[WorkerKind]]] = {
    "style": frozenset({"ui", "accessibility"}),
    "component": frozenset({"ui", "accessibility", "workflow"}),
    "route": frozenset({"ui", "accessibility", "workflow"}),
    "workflow": frozenset({"workflow", "ui", "concurrency"}),
    "api": frozenset({"api", "concurrency"}),
    "agent_tool": frozenset({"ai_agent", "api"}),
}


def allowed_workers(impact: ChangeImpactMap) -> frozenset[WorkerKind]:
    allowed: frozenset[WorkerKind] = frozenset()
    for surface in impact.surfaces:
        allowed |= WORKERS_BY_SURFACE[surface.kind]
    return allowed
