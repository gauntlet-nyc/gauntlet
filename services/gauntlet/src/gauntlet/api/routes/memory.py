"""Memory comparison: which remembered facts each Gate plan received, and which it wrote."""

from fastapi import APIRouter

from ..container import get_container
from ..schemas import MemoryRunRow, MemoryView, Provenance

router = APIRouter(prefix="/memory", tags=["memory"])

IN_PROCESS = Provenance(
    provider="memory:in_process",
    mode="offline_fixture",
    live=False,
    label="OFFLINE in-process temporal memory (same semantics); SurrealDB Agent Memory live "
    "NOT RUN",
)


@router.get("")
async def memory_view() -> MemoryView:
    gate = get_container().gate
    runs = sorted(gate.runs.values(), key=lambda r: r.created_at)
    return MemoryView(
        facts=list(gate.memory.all()),
        runs=[
            MemoryRunRow(
                run_id=r.view.run_id,
                change_id=r.view.change_id,
                status=r.view.status,
                planned_at=r.created_at.isoformat(),
                memory_fact_ids_used=r.view.memory_fact_ids_used,
                memory_facts_written=r.view.memory_facts_written,
            )
            for r in runs
        ],
        provenance=IN_PROCESS,
    )
