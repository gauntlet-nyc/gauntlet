# Architecture / boundaries

Gauntlet is one modular Python control plane plus TypeScript dashboard/test fixture. Strict hierarchy: `API → application use cases → ports → adapters`. `domain/` and `contracts/` never import a provider. `execution/` owns only sandbox/replay mechanics; `verification/` owns truth checks; `application/gate/` owns change-attributed verdict coordination; `application/recall/` owns historic-exposure, audit and counterfactual coordination. Infected history is never automatically a confirmed bad decision.

**Control plane:** authenticated scopes and approvals, Git reader, AI planning, immutable oracle registry, secrets and event log. **Test plane:** Daytona approved fixture app, fake effects only. **Browser plane:** Anchor and scoped CDP. **Replay plane:** recorded inputs/config/state and historical mock tool outputs. **Evidence plane:** sanitized artifact manifest (hashes) + SurrealDB record links + Arize trace correlation.

**Run contract:** plan freezes before worker invocation. Trusted verifier receives immutable observations, compares on equivalent fixture base/head, and records attribution separately from policy status. Repair applies hash-approved limited diffs to fresh head sandbox, replays original, variants and legitimate behaviors. Recall runs independent trigger/scope, then event audit or original-control-counterfactual.

**Scaling later:** durable orchestration queue, tenancy, signed artifact URLs, schema/SDK version registry, job cancellation/janitor, production RBAC and opt-in historical instrumentation. Do not introduce microservices until lifecycle/throughput requires it.

## Gate planning path (A-01)

`ChangeRequest → GitRepositoryInspector (analysis/) → ChangeImpactMap → AttackPlanner (planning/) → PlanValidator → FrozenPlan → RunStore "plan_frozen" event`, orchestrated by `application/gate/PlanChangeUseCase`.

- **Read-only git:** fixed subcommands via exec, no shell; per-invocation config disables external diff, textconv, fsmonitor and hooks; system/global git config ignored; diff/source/time bounds; repositories resolved from a server-side ID allowlist. `analysis/path_policy.py` keeps `.env*`, `.git`, `bench/private`, `bench/heldout`, dependencies and key material out of every impact map, excerpt and prompt.
- **Surfaces are deterministic:** `analysis/surface_mapper.py` rules map changed lines to `style/component/route/api/agent_tool/workflow`, each with line-level `SourceRef`s (pure deletions cite the base commit). Unmatched, binary, renamed-only or unparseable changes become `coverage_gaps`, never silent passes.
- **The model proposes, code decides:** `planning/worker_selector.py` derives allowed workers from surfaces. `PlanValidator` rejects non-JSON output, schema violations, wrong target/fixture, workers not allowed for the surfaces, unregistered oracles or oracles that do not support the worker, citations that touch no changed line, and attack-count/runtime overruns. Rejections are recorded with reasons.
- **Freeze before execution:** `compute_plan_hash` is SHA-256 over canonical JSON of planner version, change, impact map and accepted attacks; it is persisted in a `plan_frozen` event before any worker runs. A change with no testable surface never calls the model and records `not_tested_reason`.

## Change signals and target scope (A-02)

- `analysis/signals.py` adds line-cited `ChangeSignal`s to each surface: `auth_check_removed` / `auth_check_added` (an ownership/permission term inside a guard), `side_effect_call` (refund/charge/transfer/delete/ledger/email), `tool_definition`, `layout_positioning`. Adjacent lines merge into one ranged signal. Signals steer planning only; they are never evidence of a bug.
- `ports/targets.py` `TargetCatalog` is the server-side registry of authorized targets. `PlanChangeUseCase` refuses (`TargetNotAuthorizedError`) an unknown target or fixture **before** reading the repo or calling a model.
- `PlanValidator` rejects steps that navigate or call APIs outside the target's registered route prefixes (segment-boundary match), use an actor that is not a registered synthetic identity, or chat with an unregistered agent. The planner prompt lists only those identities, so it never needs a hidden victim ID.

## Memory-informed planning (A-07)

- `contracts/memory.py` `TemporalMemoryFact`: typed kind, summary, provenance (`finding_id`, `oracle_id`, commit, trace), `known_at` vs `valid_from/valid_until`, `supersedes`, trust. A confirmed fact must cite the finding and oracle that proved it; model summaries can never be confirmed.
- `ports/memory.py`: `MemoryReader.recall(MemoryQuery(scope, lens, surface_kinds, as_of))` and append-only `MemoryWriter.remember` — B implements them on SurrealDB Agent Memory (a separate service from core).
- `planning/memory_selection.py` re-filters whatever the store returns: confirmed + `verified_test`/`policy` trust only, known and valid at `as_of`, matching surfaces, superseded facts hidden (still stored).
- `PlanChangeUseCase.execute(..., as_of=)` pins memory visibility, so historical benchmarks cannot leak future findings; the `plan_frozen` event records `memory_fact_ids`. Memory is shown to the planner as untrusted evidence, never as an oracle or instruction.

## Voice-safe actions (A-08)

- `contracts/voice.py`: `VoiceToolCall` intents are only `run_summary`, `finding_explanation`, `inconclusive_list`, `replay_request`; approve/merge/deploy/refund/remediate are not representable. `caller_ref` comes from the verified webhook signature (C/B), not from speech.
- `VoiceBriefing` is templated from persisted findings (no model, no caller text), cites `source_event_sequence`, and always says "Not tested does not mean safe." when anything was untested or had gaps.
- `VoiceReplayRequest` starts `pending_operator_confirmation` (15 min TTL). Only `decide_replay_request` with an `AuthenticatedReviewer` on `dashboard`/`api` can confirm or decline; voice is not a valid channel, expiry is enforced, decisions are final. A confirmed request is still only a request to re-run a frozen attack, never a merge or remediation.
