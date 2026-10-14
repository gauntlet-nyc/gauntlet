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

## Event audit (A-05)

- `application/recall/event_audit.py` `EventAuditUseCase.run(recall_id, trigger, tool_name)`: only for `mode=event_audit`. Reads recorded `ToolEvent`s for the target/tool/window, asks B's `AuditEvidenceProvider` for authoritative `AuditFacts`, and classifies with `classify_event_audit`.
- **Hard rules:** an `unknown` outcome forces inconclusive; an effect reported for a non-succeeded operation is discarded and forces inconclusive; a caller/owner mismatch without an authoritative forbidden result is at most inconclusive.
- `RecallVerdict` now references `tool_event_id` (event audit) or `decision_id` (counterfactual); the contract requires the right one per mode.
- `AuditSummary` counts are computed from verdicts and must add up; an empty window is a gap ("absence of logs is not clearance").
- `RemediationProposal` is draft-only and every action is a `*_review` / evidence-collection request; there is no executed status. Violations → `reverse_transaction_review`; inconclusive → `collect_missing_evidence`. Approval for review uses the A-03 `remediation` approval subject.

## Counterfactual and materiality (A-06)

- `domain/materiality.py`: `MaterialityPolicy` (versioned) compares structured outcomes — different action, presence/absence of an amount, or amount outside `amount_tolerance_minor` is material. Free-text promises are out of scope (grounded judge + human review later).
- `application/recall/counterfactual.py` `CounterfactualUseCase.evaluate(recall_id, exposure, decision, readiness)`:
  1. not replayable (critical input missing, or `ReplayWorldResolver` cannot rebuild the environment) → `not_replayable`, no replay runs;
  2. `repeats` (≥2) control replays with every input pinned and the suspect source kept; any failed run, disagreement between runs, or mismatch with the recorded outcome → `inconclusive` and the counterfactual never runs;
  3. `repeats` counterfactual replays removing exactly the trigger source; failed or disagreeing runs → `inconclusive` (`material_change=None`);
  4. stable and material → `tainted`; stable and not material → `cleared`.
- Only document-chunk and memory triggers have a defined mutation; model/prompt/policy version triggers return `inconclusive` until a replacement-version mutation is specified.
- Every spec is deterministic (`replay_id`, `seed` per run, `logical_timestamp` = decision time) so B's engine can be audited run by run.
