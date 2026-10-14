# Recall — investigation requirements

**Two explicit modes, one shared replay substrate:**

1. `event_audit`: query recorded tool operations and authoritative event-time state. Confirm forbidden successful operations using actual outcome/transaction identity; actor-owner mismatch alone is suspicious, not proof of money destination. Replay candidate tool operations in a sealed sandbox against patch + legitimate controls.
2. `decision_counterfactual`: find provenance path from poisoned input/model/policy to historical decisions; reconstruct historical input/config/tool output/memory/KB; control replay **must match** original. Remove/replace exactly the suspect input and replay. Material outcome delta → `tainted`; no delta → `cleared`; mismatch/missing critical state → `inconclusive`/`not_replayable`.

**Historical recorder:** capture decision ID, model/prompt/policy versions, input, tool arguments and recorded outputs, KB chunk hashes, memory reads/writes + derivation, state/fixture hashes, trace, structured outcome and timestamps. Original historical records are append-only. Record missing fields and coverage.

**Graph:** `decision → retrieved → chunk`, `decision → wrote_mem → memory`, `decision → read_mem → memory`, `memory → derived_from → chunk`, `recall → affects → decision`. Same-customer linkage is not a replacement for these edges. Model version trigger may not need a poison-document link; input scope differs.

**Materiality:** code for structured outcomes/amounts and side effects; a model judge only for grounded free-text promises with cited policy. Clean regression set must remain intact. A human reviews the remediation queue; no automatic reversal/contact.

**Acceptance:** expose one indirect memory-driven decision; classify one exposed but unaffected decision; force control mismatch and missing state to inconclusive; verify historical event audit does not falsely equate invalid actor ID with money sent to attacker.
