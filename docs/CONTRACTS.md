# Contract versioning and consumer ownership

Python Pydantic DTOs in `services/gauntlet/src/gauntlet/contracts/` are canonical. Export machine JSON Schemas to `packages/contracts/jsonschema/`. Generate OpenAPI from FastAPI when endpoints exist. Frontend must generate TypeScript client, not fork types by hand. `schema_version` defaults to `1.0`; incompatible changes require an explicit v2 and an ADR.

**Stable types:** `ChangeRequest`, `SourceRef`, `ChangeImpactMap`, `AttackSpec`, `Observation`, `Finding`, `ReplaySpec`, `HistoricalDecision`, `RecallTrigger`, `RecallVerdict`, `RunEvent`. Model fields and semantic invariants are spelled out in master plan Section 5. `oracle_ids` in AttackSpec are references; an attacker cannot supply executable assertions.

**Canonical verdicts:** Gate `confirmed_regression|confirmed_pre_existing|confirmed_policy_violation|suspected|not_reproducible|environment_error|passed|not_tested`, plus attribution. Recall `audit_violation|audit_clear|tainted|cleared|inconclusive|not_replayable`; `tainted` requires matching control outcome and a material counterfactual delta, otherwise inconclusive. An absence of logged events never means audit clear without a completeness guarantee.

**API contract:** consult Section 5.2 of master plan. C owns thin FastAPI routes and generated OpenAPI export. A owns DTO changes. B assures adapter/verifier payloads satisfy them. All three review examples before Phase 1.

**Golden policy:** every schema change updates exact JSON fixtures and failing/passing contract tests; consumers test the new fixture before merge. Private benchmark truth is NEVER part of any public golden.
