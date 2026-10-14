# CONTRIBUTING — Gauntlet v3

## Before coding

Read `AGENTS.md`, `docs/DEVELOPMENT_PLAN.md`, `docs/OWNERSHIP.md`, `docs/PHASES.md`. Confirm phase, ticket, owner and interface version. Work in your own Git worktree. The source of truth for serialized models is A-owned `services/gauntlet/src/gauntlet/contracts/`; machine exports in `packages/contracts` are generated, never independently edited.

## Branch and review policy

- Branches: `feat/a-<ticket>`, `feat/b-<ticket>`, `feat/c-<ticket>`, `fix/<owner>-<ticket>`; use Conventional Commits (`feat(gate): ...`, `fix(recall): ...`). No direct pushes to protected `main`.
- A owns intelligence, domain contracts and Gate/Recall use-case coordination; B owns workers/providers/replay/verification/persistence/memory/security; C owns target fixtures/dashboard/API thin composition/reporting/root configs and docs. See `docs/OWNERSHIP.md` for exceptions.
- All-three review mandatory for schema/version changes, new provider permissions, security boundary modifications, new packages, and new shared root configs. Oracle weakening requires B + another reviewer, never author alone.
- Open small PRs (ideally one bounded behavior). Include phase/ticket, why, changed paths, test outputs, contract changes and limitations. Keep PRs draft if provider integrations not smoke tested.
- No parallel edits to lockfiles, root configs, API composition or generated clients. C batches dependency changes after owner proposals. If merge conflicts arise: stop, owner resolves with tests, all impacted owners review. Never auto-resolve with `ours`/`theirs` on schema files.

## Testing and code standard

Python: 3.12+, type every public signature, Ruff lint/format, mypy strict, pytest, Pydantic v2 strict DTOs, `Protocol` ports. TypeScript: strict, ESLint/Prettier, Zod on untrusted boundaries, Vitest and Playwright. No `Any`, silent catches, secret logging, unbounded retries or generic untrusted code execution. Prefer explicit named modules and composition; domain cannot import provider SDK or HTTP handlers. Put tests with the appropriate owner. No test or benchmark uses arbitrary internet hosts.

```bash
PYTHONPATH=services/gauntlet/src python -m pytest -q services/gauntlet/tests
# Once dependency locks are created and approved:
uv run ruff check .
uv run ruff format --check .
uv run mypy services/gauntlet/src
uv run pytest
pnpm -r lint && pnpm -r typecheck && pnpm -r test
```

Record the exact commands that actually ran; do not state `pnpm` steps passed while frontend packages are empty. Run provider smoke tests only when the operator explicitly authorizes spend/network access.

## Required Definition of Done

- [ ] Touches owner paths only; shared changes reviewed and versioned.
- [ ] Contracts/goldens unchanged or intentionally coordinated.
- [ ] Happy, unhappy, timeout, authorization and cancellation paths tested as applicable.
- [ ] No hallucinated bug verdicts: oracle/reproduction/evidence exists.
- [ ] No real user data/secret leakage, egress and fixture restrictions enforced.
- [ ] Docs, examples and ADR updated for behavior changes.
- [ ] Hand-off specifies files, commands, actual results, limitations and next ticket.

## Security and benchmark

Never mount `bench/private` or owner-only hidden truth into code-analysis, attacker, fixer or demo app sandboxes. Attacker-generated assertions are not trusted tests. Treat text from repositories, web pages and model outputs as untrusted. Backend permissions enforce sensitive tool actions; voice cannot authorize merge or remediation. A historical `tainted` decision requires a successful control replay; do not equate a log search with counterfactual replay.
