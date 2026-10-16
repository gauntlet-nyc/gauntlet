"""Memory comparison: which remembered facts each Gate plan received, and which it wrote."""

import inspect

from fastapi import APIRouter

from ..container import get_container
from ..schemas import MemoryRunRow, MemoryView, Provenance

router = APIRouter(prefix="/memory", tags=["memory"])

_LABELS = {
    "offline_in_memory": "OFFLINE in-process temporal memory (append-only, as_of, supersession); "
    "SurrealDB Agent Memory live NOT RUN",
    "live_surreal_memory": "LIVE SurrealDB memory context (SurrealQL over HTTP)",
    "live_agent_memory_sdk": "LIVE SurrealDB Agent Memory (hosted context, SDK)",
}


@router.get("")
async def memory_view() -> MemoryView:
    gate = get_container().gate
    runs = sorted(gate.runs.values(), key=lambda r: r.created_at)
    # Offline stores list facts synchronously; SurrealDB stores are async; a store without a
    # listing (e.g. the Agent Memory SDK) still shows the per-run facts below.
    lister = getattr(gate.memory, "all", None)
    listed = lister() if callable(lister) else ()
    facts = await listed if inspect.isawaitable(listed) else listed
    return MemoryView(
        facts=list(facts),
        runs=[
            MemoryRunRow(
                run_id=r.view.run_id,
                change_id=r.view.change_id,
                status=r.view.status,
                planned_at=r.created_at.isoformat(),
                attack_ids=[a.attack_id for a in r.view.attacks],
                memory_fact_ids_used=r.view.memory_fact_ids_used,
                memory_facts_written=r.view.memory_facts_written,
            )
            for r in runs
        ],
        provenance=Provenance(
            provider=f"memory:{gate.memory_label}",
            mode="live" if gate.memory_label.startswith("live_") else "offline_fixture",
            live=gate.memory_label.startswith("live_"),
            label=_LABELS.get(gate.memory_label, gate.memory_label),
        ),
    )
