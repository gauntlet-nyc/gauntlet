# GAUNTLET v3 — Product design authority

**Core:** Gate proactively tests code changes before release. Recall retrospectively investigates already-live failures using historical events and reproducible decision lineage. They share sandboxes, replay, evidence, verification and temporal memory but must not share verdict semantics.

**Why it matters:** normal CI checks expected cases; Gauntlet explores changes and invents contextual adversarial hypotheses. Reproducible oracles, base/head comparison, trace evidence and human-reviewed repair turn guesses into defensible findings. Recall asks which historical actors/decisions were exposed, whether real violations occurred, and—in faithful agent counterfactual mode—whether removing suspect information materially changes a reproducible past decision.

**Supported surfaces over time:** responsive UI, accessibility, workflows, REST APIs, authorization, concurrency/state integrity, agent prompts/retrieval/tool permissions and optionally voice. **Not** a payment-specific product. No universal correctness claim.

**Canonical example:** `PR A` adds Help button that covers Checkout at mobile viewport; `PR B` changes refund tool authorization, enabling synthetic cross-user refund. A third historical seeded scenario explores a wrong refund rule in KB/memory. Honest failure classification and independent evidence are more important than raw attack count.

**Sponsor mapping:** Daytona for isolation/replay; Anchor for browser actions; Arize for traces and experiments; SurrealDB core for run graph and historical lineage, Agent Memory for typed, temporal, source-backed shared learnings; ElevenLabs for authorized interactive evidence briefings. See `docs/DEVELOPMENT_PLAN.md` for architecture, explicit contracts, phases and safety standards.
