"""Live smoke for SurrealDB core (run store + lineage) and the memory context.

Needs RUN_LIVE_INTEGRATIONS=1 and SURREAL_* (and SURREAL_MEMORY_* for --memory).
Writes only synthetic records under a fresh run/fact ID. Prints IDs and status, no values.
"""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4

from gauntlet.contracts import (
    LineageEdge,
    MemoryProvenance,
    NodeRef,
    RunEvent,
    TemporalMemoryFact,
)
from gauntlet.memory.surreal_memory import SurrealTemporalMemory
from gauntlet.persistence.factory import core_client, memory_client
from gauntlet.persistence.surreal_store import (
    SurrealLineageStore,
    SurrealRunStore,
    apply_core_schema,
)
from gauntlet.ports.memory import MemoryQuery
from gauntlet.settings import SettingsError, load_settings, require_live


async def _core(report: dict[str, object]) -> None:
    client = core_client(load_settings())
    try:
        await apply_core_schema(client)
        run_id = f"smoke-{uuid4().hex[:12]}"
        now = datetime.now(UTC)
        store = SurrealRunStore(client)
        await store.append_event(
            RunEvent(
                run_id=run_id,
                event_id="e0",
                sequence=0,
                created_at=now,
                actor="smoke",
                event_type="smoke_started",
            )
        )
        events = await store.list_events(run_id)
        lineage = SurrealLineageStore(client)
        chunk = NodeRef(kind="document_chunk", node_id=f"{run_id}-chunk")
        decision = NodeRef(kind="decision", node_id=f"{run_id}-decision")
        await lineage.record_edge(
            LineageEdge(
                edge_id=f"{run_id}-edge",
                source=chunk,
                relation="retrieved_by",
                target=decision,
                recorded_at=now,
            )
        )
        report["core"] = {
            "run_id": run_id,
            "events_read_back": len(events),
            "edges_read_back": len(await lineage.edges_from(chunk)),
            "status": "passed" if len(events) == 1 else "failed",
        }
    finally:
        await client.close()


async def _memory(report: dict[str, object]) -> None:
    client = memory_client(load_settings())
    try:
        memory = SurrealTemporalMemory(client)
        await memory.ensure_schema()
        now = datetime.now(UTC)
        fact_id = f"smoke-{uuid4().hex[:12]}"
        await memory.remember(
            TemporalMemoryFact(
                fact_id=fact_id,
                kind="ui_occlusion",
                summary="smoke fact (synthetic)",
                verification="unverified",
                trust="app_content",
                scope="smoke",
                surface_kinds=("component",),
                source=MemoryProvenance(),
                known_at=now,
                valid_from=now,
            )
        )
        found = await memory.recall(
            MemoryQuery(
                scope="smoke",
                lens="investigator",
                surface_kinds=frozenset({"component"}),
                as_of=now,
            )
        )
        report["memory"] = {
            "fact_id": fact_id,
            "status": "passed" if any(f.fact_id == fact_id for f in found) else "failed",
        }
    finally:
        await client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory", action="store_true", help="also smoke the memory context")
    args = parser.parse_args()
    report: dict[str, object] = {"mode": "live_surreal_smoke"}
    try:
        require_live(load_settings())
        asyncio.run(_core(report))
        if args.memory:
            asyncio.run(_memory(report))
    except SettingsError as exc:
        report["status"] = "not_run"
        report["error"] = str(exc)
        print(json.dumps(report, indent=2))
        raise SystemExit(2) from None
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
