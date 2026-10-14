# Recall — investigation requirements

**Two explicit modes, one shared replay substrate:**

1. `event_audit`: query recorded tool operations and authoritative event-time state. Confirm forbidden successful operations using actual outcome/transaction identity; actor-owner mismatch alone is suspicious, not proof of money destination. Replay candidate tool operations in a sealed sandbox against patch + legitimate controls.
2. `decision_counterfactual`: find provenance path from poisoned input/model/policy to historical decisions; reconstruct historical input/config/tool output/memory/KB; control replay **must match** original. Remove/replace exactly the suspect input and replay. Material outcome delta → `tainted`; no delta → `cleared`; mismatch/missing critical state → `inconclusive`/`not_replayable`.

**Historical recorder:** capture decision ID, model/prompt/policy versions, input, tool arguments and recorded outputs, KB chunk hashes, memory reads/writes + derivation, state/fixture hashes, trace, structured outcome and timestamps. Original historical records are append-only. Record missing fields and coverage.

**Graph:** `decision → retrieved → chunk`, `decision → wrote_mem → memory`, `decision → read_mem → memory`, `memory → derived_from → chunk`, `recall → affects → decision`. Same-customer linkage is not a replacement for these edges. Model version trigger may not need a poison-document link; input scope differs.

**Materiality:** code for structured outcomes/amounts and side effects; a model judge only for grounded free-text promises with cited policy. Clean regression set must remain intact. A human reviews the remediation queue; no automatic reversal/contact.

**Acceptance:** expose one indirect memory-driven decision; classify one exposed but unaffected decision; force control mismatch and missing state to inconclusive; verify historical event audit does not falsely equate invalid actor ID with money sent to attacker.

## Implemented contracts and semantics (A-04)

- **Lineage graph** (`contracts/lineage.py`): `NodeRef` + `LineageEdge` in the direction of influence. Only these edges exist: `document_chunk -retrieved_by-> decision`, `decision -wrote-> memory`, `memory -read_by-> decision`, `document_chunk -derived_into-> memory`, `{model,prompt,policy}_version -configured-> decision`, `decision -produced-> tool_event`. Anything else is rejected at the contract.
- **`ToolEvent`**: recorded tool operation; `outcome='unknown'` is neither success nor failure.
- **`ExposureRecord`**: connected path from the trigger node to the decision; `direct` iff one edge. Exposure is not harm.
- **Scoping** (`application/recall/scope.py`): breadth-first over recorded edges from the trigger node (document, memory, model/prompt/policy version), so each decision gets its shortest provenance path. Only decisions on the trigger's target and inside the incident window are exposures; edges recorded after the window are ignored (no hindsight). Hop/node limits, and edges to unrecorded decisions, become explicit gaps. `finding` and `tool_result_window` triggers are routed to event audit.
- **Replay readiness** (`application/recall/readiness.py`): `tool_results_hash` and `input_messages_hash` are always critical; `kb_snapshot_hash` becomes critical if the decision retrieved KB content and `memory_snapshot_hash` if it read memory, even when the recorder flagged them optional. Any critical gap → not replayable (still exposed, manual review).
- Ports `LineageStore` and `HistoricalEventStore` are read-only; B implements them on SurrealDB core.
