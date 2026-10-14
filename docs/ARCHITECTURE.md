# Architecture / boundaries

Gauntlet is one modular Python control plane plus TypeScript dashboard/test fixture. Strict hierarchy: `API → application use cases → ports → adapters`. `domain/` and `contracts/` never import a provider. `execution/` owns only sandbox/replay mechanics; `verification/` owns truth checks; `application/gate/` owns change-attributed verdict coordination; `application/recall/` owns historic-exposure, audit and counterfactual coordination. Infected history is never automatically a confirmed bad decision.

**Control plane:** authenticated scopes and approvals, Git reader, AI planning, immutable oracle registry, secrets and event log. **Test plane:** Daytona approved fixture app, fake effects only. **Browser plane:** Anchor and scoped CDP. **Replay plane:** recorded inputs/config/state and historical mock tool outputs. **Evidence plane:** sanitized artifact manifest (hashes) + SurrealDB record links + Arize trace correlation.

**Run contract:** plan freezes before worker invocation. Trusted verifier receives immutable observations, compares on equivalent fixture base/head, and records attribution separately from policy status. Repair applies hash-approved limited diffs to fresh head sandbox, replays original, variants and legitimate behaviors. Recall runs independent trigger/scope, then event audit or original-control-counterfactual.

**Scaling later:** durable orchestration queue, tenancy, signed artifact URLs, schema/SDK version registry, job cancellation/janitor, production RBAC and opt-in historical instrumentation. Do not introduce microservices until lifecycle/throughput requires it.
