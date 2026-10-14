# Copy-ready handoffs for A/B/C agents

**Shared preamble (prepend to every task):**

> Implement Gauntlet v3 under `AGENTS.md`, `docs/DEVELOPMENT_PLAN.md`, `docs/OWNERSHIP.md` and `docs/PHASES.md`. You are owner **[A/B/C]**. Task **[ticket]**, phase **[P#]**. Edit only owned paths. Read frozen contracts and golden JSON before editing. Do not guess sponsor SDK APIs or use production data. Write tests for success/failure and explain the gate with exact command outputs. If a producer DTO or security policy must change, STOP and request a three-person contract/ADR review; do not patch somebody else's files. Mocks can support offline tests but cannot count as live sponsor integration. Never present model conjecture as a verified finding or historical exposure as proven causation.

## A — Product intelligence/contracts

**A-00 prompt:** Implement Pydantic contracts and versioned JSON Schema for Gate and Recall DTOs, including strict `AttackSpec` with registered oracle IDs, immutable evidence references, `ReplaySpec`, and `RecallVerdict` classifications. Add golden JSON specimens. Implement pure `classify_gate` and `classify_counterfactual` with tests for regression/pre-existing, control mismatch and material/no material change. Propose type changes through ADR, request B/C review, and commit only your owned files.

**A-01 prompt:** Implement a bounded read-only Git inspector and impact mapper for changed source lines, affected components/routes/tool endpoints and grounded source references. Feed normalized evidence to a model gateway interface and validate returned attack specs against known worker/oracle registries. Persist plan before any action. Test a UI PR and AI tool PR choose different worker kinds with no hidden exploit labels.

**A-04 to A-06 prompt:** Implement Recall application workflow and lineage-based scope with distinct `event_audit` and `decision_counterfactual` branches. Audit requires real side-effect evidence; counterfactual requires matching control. Report incomplete coverage/missing history without guessing. Coordinate exact replay spec with B.

## B — Sandbox, test workers, memory and verifier

**B-00 prompt:** Validate docs/API versions (Daytona, Anchor, Arize, SurrealDB core and Agent Memory, Bedrock); record results in SDK_VALIDATION.md. Implement offline fake ports and independent registered oracle with no dynamic untrusted predicates. Do not edit DTOs; raise interface PR requests instead.

**B-01 prompt:** Given frozen UI golden and allowed Daytona fixture IDs, provision equivalent base/head target copies, control browser with Anchor, resize and collect DOM geometry/hit-test/click results. Repeat and validate via trusted oracle. Use a real provider in opt-in smoke only, with sanitization and teardown. Never leak benchmark truth or accept arbitrary URL redirects.

**B-02 prompt:** Implement synthetic AI chat/tool worker and backend authz oracle. Record actual tool calls, authenticated actor IDs and state transition. Classify unsafe side effect, not merely LLM promises. Emit Arize OpenInference spans with real IDs if provider configured; otherwise report offline-only.

**B-04 to B-07 prompt:** Implement immutable historical event capture and Surreal graph edges. Build event audit and control/counterfactual replay on the shared sandbox engine. Introduce typed time-aware Agent Memory (separate SDK) with as-of, provenance and supersession tests. Ensure no LLM judge can override an objective backend outcome.

## C — Fixture, dashboard, API and team DX

**C-00 prompt:** Set up monorepo toolchain, CI and contributor docs. Implement `/health`, typed FastAPI route composition and fake-run page. Build Cartwheel app manifest and synthetic fixture plan with real Git refs, never attacker-readable answer labels. Do not introduce new provider-specific SDKs without B's validation.

**C-01 to C-03 prompt:** Implement target Help-button and AI-tool PRs, dashboard trace/evidence UI, approval flows and repair verification status. The app's hidden flaws must be evaluated outside attacker checkout; the public app may contain vulnerable source because that is precisely what analyzer must inspect. Preserve functional feature after repairs.

**C-04 to C-08 prompt:** Build synthetic 7-day historical activity and poisoned KB/memory demo fixture, Recall graph and case review UI, and ElevenLabs read-only evidence conversation/webhook. Don't present seeded target totals as measured until actual queries return results. Voice request must never merge/approve production actions.

## Integration cadence

At beginning of each phase: 20-minute contract/interface review + acceptance goldens. Mid-phase: consumer tests against mocks. End: B and C integration with A verifying product semantics. C drives integration PR. Open ticket references on every cross-owner change; if time constrained, prefer reduced scope with real proof over a broader synthetic UI.
