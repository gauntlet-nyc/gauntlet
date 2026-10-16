# Tenancy and authorization policy (P10 design)

Status: **design + tests for the policies that exist today**. Multi-tenant isolation,
production RBAC and SSO are **not implemented**. The demo runs as one tenant with dev-grade
reviewer tokens. Nothing in this document is a claim that a missing control exists.

## 1. Principals

| Principal | How it is authenticated today | What it may do |
|---|---|---|
| Reviewer (human) | Dev-grade server-side token table `GAUNTLET_REVIEWER_TOKENS=name:token,...`; the CLI reads the presented token from `GAUNTLET_REVIEWER_TOKEN`, the API from `Authorization: Bearer` | Approve or reject one scope / fix plan / remediation **hash**; never merge |
| Planner model | None (it is not a principal) | Propose JSON. Everything it says is untrusted data |
| Attack worker | Composition root wiring | Execute a frozen, validated plan in one registered environment |
| Oracle | Composition root wiring; registry is read-only | Read stored evidence, emit verdicts |
| Voice caller | Signed webhook (Session 2/3) | Read-only lookups; **cannot approve** (`ApprovalChannel` has no voice value) |
| GitHub App | Webhook signature (Session 3) | Create a ChangeRequest and publish a check run; never write code |

## 2. Tenancy model (target design)

* A **tenant** owns repositories, targets, fixtures, runs, evidence, memory and history.
* Every record carries `tenant_id`; every port call is scoped by the tenant of the caller.
  Today the only tenant is implicit (`cartwheel-fixture` target, synthetic data only).
* Target registration is operator-owned configuration (manifest + snapshot registration),
  never request input. A run can only name a registered `target_id`/`fixture_id`.
* Memory scope is `project/<target_id>`; recall never crosses scopes (enforced by
  `MemoryQuery.scope` and re-checked by the in-memory/Surreal adapters).
* Evidence is addressed by store-assigned `artifact_id` and bound to
  `run_id/attempt_id/observation_id/environment_id/source_sha/fixture_checksum/step`.
  A future multi-tenant store adds `tenant_id` to that binding; cross-tenant reads must
  fail as "not found".
* Secrets are environment-only (`gauntlet.settings`), never stored on records, never sent to
  sandboxes, browsers or models.

## 3. Authorization rules (enforced today)

| # | Rule | Where | Test |
|---|---|---|---|
| A1 | Only operator-registered targets and fixtures can be planned or run | `PlanChangeUseCase`, `StaticTargetCatalog`, sandboxes | `test_s1_policies.py::test_unregistered_target_is_refused` |
| A2 | Model proposals are validated: registered oracle, allowed worker for the changed surface, citation of a changed line on base/head, registered routes/actors/agents | `PlanValidator` | `test_s1_policies.py::test_plan_validator_policies` |
| A3 | A fix may only write non-protected paths it was approved for (no tests, oracles, bench, CI, lockfiles, secrets) | `is_patch_path_allowed`, `approval_mismatches`, patch runner | `test_s1_policies.py::test_patch_path_policy` |
| A4 | Approvals bind run, subject, exact SHA-256, target, fixture, paths; expire (≤ 24 h); single use; voice cannot approve | `ApprovalService`, `ApprovalRecord` | `test_s1_policies.py::test_approval_policies`, `test_s1_repair.py` |
| A5 | No confirmed Gate finding without two hard-oracle head reproductions and head/base attribution | `Finding`, `classify_gate`, `adjudicate_*_pair` | `test_s1_policies.py::test_confirmed_finding_needs_evidence` |
| A6 | No Recall `tainted` without a matching control and a material counterfactual | `RecallVerdict` validator, `CounterfactualUseCase` | `test_s1_policies.py::test_tainted_needs_control_and_material_change` |
| A7 | Memory used for planning must be confirmed, trusted, known and valid at `as_of`, not superseded | `select_memory` | `test_s1_policies.py::test_memory_selection_policies` |
| A8 | Browser and API workers stay on the environment's exact origin; redirects are blocked | local/Anchor browser adapters, `HttpxApiClient` | `test_b01_local_browser.py`, `test_s1_p9_workers.py` |
| A9 | Secrets never print; missing keys fail with the variable name only | `gauntlet.settings.Secret`, `MissingSettingError` | `test_s1_run_gate.py::test_settings_never_reveal_secrets` |

## 4. Not implemented (explicit gaps)

* `tenant_id` on records and ports; per-tenant stores and quotas.
* Reviewer identity from an IdP (OIDC/SAML), roles (viewer / reviewer / admin), audit export.
* Approval quorum (two reviewers) for high-severity fixes.
* Rate limits and cost budgets per tenant beyond per-plan runtime and attack caps.
* Key rotation and per-tenant provider credentials.

Each gap needs its own design review and tests before it is claimed.
