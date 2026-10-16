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

## Live Recall access

The `/recall/audit`, `/recall/counterfactual`, `/recall/lineage/{decision_id}` and
`/recall/review-queue` reads can start replay work. They require the existing reviewer
bearer token whenever the composed Recall runtime uses a live provider. Missing or invalid
credentials return HTTP 401 before replay starts, including requests for cached results.
Offline synthetic replay remains public; `/recall/timeline` only reads recorded history.
The dashboard forwards its httpOnly reviewer cookie in server-side requests and directs
unauthenticated live Recall visitors to reviewer login.

For live use, configure `GAUNTLET_REVIEWER_TOKENS=name:token` with a token of at least
16 characters and `RUN_LIVE_INTEGRATIONS=1`. For Azure, set
`GAUNTLET_MODEL_PROVIDER=azure`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`,
and `AZURE_OPENAI_API_KEY`. For Bedrock, set `GAUNTLET_MODEL_PROVIDER=bedrock`,
`AWS_REGION`, `BEDROCK_MODEL_ID`, and working AWS credentials through the standard
credential chain (for example `AWS_PROFILE`, or `AWS_ACCESS_KEY_ID` plus
`AWS_SECRET_ACCESS_KEY` and `AWS_SESSION_TOKEN` for temporary credentials).
Restart the API after configuration changes, then sign in at `/login` using that token.
Direct API callers supply `Authorization: Bearer <token>`. Never put tokens in URLs.
The route guard is covered by `test_c3_api.py::test_live_recall_rejects_missing_or_invalid_auth_before_replay`.

## 4. Not implemented (explicit gaps)

* `tenant_id` on records and ports; per-tenant stores and quotas.
* Reviewer identity from an IdP (OIDC/SAML), roles (viewer / reviewer / admin), audit export.
* Approval quorum (two reviewers) for high-severity fixes.
* Rate limits and cost budgets per tenant beyond per-plan runtime and attack caps.
* Key rotation and per-tenant provider credentials.

Each gap needs its own design review and tests before it is claimed.
