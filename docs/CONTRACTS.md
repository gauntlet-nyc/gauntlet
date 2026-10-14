# Contract versioning and consumer ownership

Python Pydantic DTOs in `services/gauntlet/src/gauntlet/contracts/` are canonical. Export machine JSON Schemas to `packages/contracts/jsonschema/` with `scripts/export_schemas.py`; the exported set is the single list in `contracts/registry.py`, and `tests/test_schema_export.py` fails if a committed schema is stale or orphaned. Generate OpenAPI from FastAPI when endpoints exist. Frontend must generate TypeScript client, not fork types by hand. `schema_version` defaults to `1.0`; incompatible changes require an explicit v2 and an ADR.

**Stable types (v1, A-00):** `ChangeRequest`, `SourceRef`, `ChangeImpactMap`, `AttackSpec` (+ typed steps), `Observation` (+ `ActionRecord`, `ToolCallRecord`), `OracleVerdict`, `Finding`, `ReplaySpec`, `ReplayResult`, `HistoricalDecision`, `RecallTrigger`, `RecallVerdict`, `RunEvent`, `EvidenceRef`, `MissingInput`. A-03 adds `FixPlan`, `ApprovalDecision`, `ApprovalRecord`. Deferred to their phases: `ExposureRecord` (A-04), `RemediationProposal` (A-05), `TemporalMemoryFact` (A-07).

**Where things live:** verdict/status vocabularies are `StrEnum`s in `domain/statuses.py` (stdlib only) and are re-used by the DTOs, so there is exactly one definition of every verdict. Pure classifiers are in `domain/verdicts.py`. Async `Protocol` ports for B's adapters and fakes are in `ports/`, with typed errors in `ports/errors.py`.

## Wire rules enforced by the models

- Every model: `extra="forbid"`, frozen, bounded strings/lists, timezone-aware timestamps only.
- IDs match `^[A-Za-z0-9][A-Za-z0-9._:-]*$` (≤128). Git SHAs are 7–64 lowercase hex; content hashes are 64-hex SHA-256.
- `SourceRef.path` is repository-relative (no absolute paths, `..`, `.`, backslashes or drive letters) and `end_line >= start_line`.
- `AttackSpec.steps` is a discriminated union on `action`. Each step accepts only its own fields: `navigate` takes an origin-relative `path` (no scheme, no `//host`, no `..`); `test_api` and `chat` require a synthetic `actor_id`. There is no shell, JS, SQL or free URL step.
- `oracle_ids` are dotted references (`ui.primary_action_reachable`), unique per spec; executable assertions cannot be expressed.
- `ChangeRequest.max_cost_usd_cents` is mandatory (integer minor units).
- `RunEvent.event_type` is snake_case; `payload` is a flat map of scalars; `idempotency_key` and `snapshot_id` are optional envelope fields.

## Approval invariants (A-03)

- An approval binds to **one** `run_id`, `subject` (`scope`/`fix_plan`/`remediation`), `subject_id`, exact `plan_sha256`, `target_id` and `fixture_id`, and expires within 24h (default TTL 2h).
- `channel` is `dashboard` or `api`; there is no voice channel, so voice can never approve.
- `FixPlan.allowed_paths` and approved `fix_plan` records may only name patchable paths: never tests, oracles/verification, `bench/`, `.github/`, lockfiles or secrets (`domain/path_policy.py`).
- `fix_plan_hash(plan)` covers everything except `created_at`; any edit to the diff, paths or test plan changes it, so an old approval cannot authorize a modified patch.
- Approving a hash that is no longer current raises `StaleApprovalError`. `ApprovalService.authorize` checks every field, expiry, decision and touched paths, then **spends** the approval (single use).
- Run lifecycles (`domain/state.py`) have no merged/released/deployed state; `planned → executing` and `fix_pending → patching` are impossible without the approval states in between.

## Verdict invariants (the contract refuses impossible claims)

| Claim | Requires |
|---|---|
| any `confirmed_*` Finding | `head_reproductions >= 2`, ≥1 oracle verdict ID, ≥1 evidence ID |
| `confirmed_regression` | base attempted, zero base reproductions, attribution `introduced` |
| `confirmed_pre_existing` | ≥1 base reproduction, attribution `pre_existing` |
| `passed` | zero head reproductions |
| `tainted` RecallVerdict | mode `decision_counterfactual`, `control_matches=true`, `material_change=true`, replay IDs |
| `cleared` RecallVerdict | mode `decision_counterfactual`, `control_matches=true`, `material_change=false`, replay IDs |
| `audit_violation` | mode `event_audit`, evidence IDs, no replay control fields |
| `historical_*`/`event_audit` ReplaySpec | `decision_id` |
| `historical_counterfactual` ReplaySpec | excluded or replacement source + `mutation_description` (control replays may not mutate) |

The classifiers in `domain/verdicts.py` produce these outcomes: `classify_gate` (environment/fixture mismatch → `environment_error`; non-hard oracle → `suspected`; <2 reproductions → `suspected`/`not_reproducible`; no base run → `confirmed_policy_violation`/`unknown`), `classify_counterfactual`, and `classify_event_audit` (incomplete logs or unchecked authoritative state → `inconclusive`).

**Canonical verdicts:** Gate `confirmed_regression|confirmed_pre_existing|confirmed_policy_violation|suspected|not_reproducible|environment_error|passed|not_tested`, plus attribution. Recall `audit_violation|audit_clear|tainted|cleared|inconclusive|not_replayable`. An absence of logged events never means audit clear without a completeness guarantee.

**API contract:** consult Section 5.2 of master plan. C owns thin FastAPI routes and generated OpenAPI export. A owns DTO changes. B assures adapter/verifier payloads satisfy them. All three review examples before Phase 1.

**Golden policy:** every file in `docs/contracts/examples/` is mapped to a model in `tests/test_goldens.py` and must round-trip exactly; an unmapped file fails the suite. Every schema change updates exact JSON fixtures and failing/passing contract tests; consumers test the new fixture before merge. Private benchmark truth is NEVER part of any public golden.
