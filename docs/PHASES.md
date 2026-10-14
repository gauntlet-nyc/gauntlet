# Milestones, dependency gates and work tickets

**Rule:** advance on proven acceptance, not elapsed hours. Core gates are nonnegotiable; productization takes as long as required. A/B/C refer to `docs/OWNERSHIP.md`. Unimplemented files are planned, never counted as completed.

| Phase | Purpose | A ticket | B ticket | C ticket | Required joint gate |
|---|---|---|---|---|---|
| P0 | Dev platform + frozen contracts | `A-00` DTOs/ports/goldens | `B-00` fake providers + safety oracle + SDK probes | `C-00` root workspace/CI, `/health`, fixture stub | Offline smoke end-to-end, no provider keys; all contracts agreed |
| P1 | Gate UI | `A-01` Git impact map and planner | `B-01` Daytona/Anchor UI worker + occlusion oracle | `C-01` floating Help test PR + run screen | Blind viewport selection, blocked Checkout head, clean base |
| P2 | Gate AI/tool | `A-02` tool permission impact/planning | `B-02` AI worker, trusted ledger oracle, Arize spans | `C-02` synthetic assistant tool/owner actors | Same planner chooses AI vs UI, actual forbidden action observed |
| P3 | Repair | `A-03` approval/plan state machine | `B-03` patch runner + variants + legit checks | `C-03` review UI and reports | Approved patch fixes exploit, preserves feature, no auto-merge |
| P4 | Historical logging | `A-04` historical DTO/lineage policy | `B-04` event recorder, Surreal graph, coverage checks | `C-04` synthetic history and KB/memory fixture | Immutable events have provenance and missing fields classified |
| P5 | Recall event audit | `A-05` audit scope/coordinator | `B-05` query + side-effect evidence + patched operation replay | `C-05` audit card/review queue | Confirmed harms use actual results, not caller mismatch alone |
| P6 | Recall counterfactual | `A-06` investigator and materiality semantics | `B-06` pinned control + counterfactual replay and Arize experiments | `C-06` poisoned KB/memory history graph UI | Direct+second order, tainted+cleared+inconclusive demonstrated |
| P7 | Temporal memory | `A-07` memory-informed planning contract | `B-07` Agent Memory integration, supersession/as-of tests | `C-07` reused-memory comparison screen | New change benefits from verified history with citations |
| P8 | Voice/sponsors | `A-08` voice-safe action contract | `B-08` webhook auth/evidence integrity | `C-08` ElevenLabs interaction, sponsor proof UI | Real spoken evidence lookup; no voice-only approval |
| P9 | CI/generalization | `A-09` GitHub integration/AST mapping | `B-09` API/workflow/accessibility/concurrency workers | `C-09` target onboarding wizard/check run UI | Held-out different repo supports useful real new test |
| P10 | Hardening | `A-10` tenant/auth policies | `B-10` durable jobs/cost, retention, recovery | `C-10` ops dashboards/product UX | Recovery/isolation/privacy tests and external security review |

## P0 exact tasks

**A-00**: introduce strict Pydantic `ChangeRequest/ImpactMap/AttackSpec/Observation/Finding/ReplaySpec/HistoricalDecision/RecallTrigger/RecallVerdict/RunEvent`; add goldens and schema export; implement pure Gate/Recall classification with tests. Contract examples must not include hidden truth. **B-00**: implement mock sandbox, browser, store, replay, registered oracle; validate one positive/negative classification, rejection of forbidden action and missing replay history. Start provider smoke log. **C-00**: Compose/local setup policy, `/health`, root CI, fixture manifest with synthetic identities, simple typed API example. **Gate:** A's golden plan can be consumed by B's fake worker and displayed as an API response by C, with no provider key and no shared-file edits.

## P1 exact tasks

**A-01**: bounded Git hunk parsing, source-line citations, change-to-surface graph, per-hypothesis `why_this_change`, planner schema validation, freeze-before-execution. **B-01**: Daytona base/head environments, same fixture checksum, Anchor viewport/actions, DOM bounding rect + elementFromPoint + actual click, screenshots/recording, repeat head and base. **C-01**: Help component and Checkout CTA with real base/head SHAs, site manifest, screenshot/trace evidence page. **Gate:** objective mobile obstruction on head, accessible CTA on base; bug description not visible to planner; record zero/unknown findings honestly for unaffected PR.

## P2 exact tasks

**A-02**: tool schema and backend ownership boundary mapped from diff; AI worker selection; prompts independent of hidden victim ID. **B-02**: synthetic chat/tool executor, authorized vs unauthorized call traces, state/ledger checks, Arize spans. **C-02**: synthetic owners/orders, target `request_refund`, safe fake ledger, normal owner success path. **Gate:** actual forbidden side effect on head is confirmed; prompt-only verbal promise doesn't count as money moved; authentic owner remains allowed.

## P3 exact tasks

**A-03**: scope + plan hash approval state machine, human identity and audit DTO. **B-03**: patch executor in fresh isolated tree with file allowlist, oracle access read-only, re-run original+variant+normal feature+test suite. **C-03**: findings, patch-diff and approval UI, review-only release verdict. **Gate:** one real patch SHA with reproducible before/after evidence; neither Help nor refunds completely disabled.

## P4 exact tasks

**A-04**: decision lineage contracts, hashes, missing-data semantics. **B-04**: `DecisionRecorder`, Surreal graph edges and immutable snapshot metadata, coverage checks. **C-04**: synthetic historical event history and KB memory write/read fixtures with fixed seeds. **Gate:** a past decision links to a KB chunk, one memory write and downstream read; a deliberately missing historical tool result marks not replayable.

## P5 exact tasks

**A-05**: Recall trigger/scope, event audit policy and review queue semantics. **B-05**: time-bounded event query, actual action success/transaction/destination check, patched-event replay with clean regression controls. **C-05**: history audit timeline/report; review-queue approval only. **Gate:** reports observed violations with definitive vs insufficient evidence classes; replay preserves authorized effects.

## P6 exact tasks

**A-06**: investigator scope for direct/second-order poison and materiality rules. **B-06**: pin replay world, run original/control/counterfactual, enforce control match, Arize experiments and repeat noisy cases. **C-06**: invented poisoned document in demo history and evidence UX with tainted, cleared and inconclusive cases. **Gate:** at least one confirmed flip, one unaffected exposed decision, one control mismatch + one missing-state inconclusive.

## P7 exact tasks

**A-07**: typed memory retrieval injected into planner/investigator, no hindsight. **B-07**: separate SurrealDB Agent Memory client with provenance, scope/lens, as_of and supersession tests. **C-07**: memory provenance timeline + with/without tests comparison. **Gate:** an old finding improves new hypothesis selection while stale memory remains historically inspectable.

## P8–P10 exact tasks

Voice: secure signed webhook/signed URL and read-only investigation; audit request to replay requires authenticated operator; proof for each sponsor. Generalization: GitHub App read-only checks, AST-assisted analysis, more workers and held-out benchmark. Hardening: durable queue, tenant isolation, protected historical PII, key rotation, SLO/cost management and recovery drills. Gate each with actual provider and security tests; no mock labeled real.

## First integration checkpoint

Joint `A-00 + B-00 + C-00`: use one frozen `AttackSpec` golden, execute mock observation, evaluate hard oracle, persist run event in fake store, fetch via thin API. This single shared checkpoint is intentionally small and avoids giant conflicting integration branches.
