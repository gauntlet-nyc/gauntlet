# Gauntlet — Gate + Recall (unified v3 starter)

**Status: implementation starter, NOT an operational testing/recall product.** The included `/health` route, Pydantic contracts, pure verdict functions and offline tests are functional scaffolding. Daytona/Anchor/Arize/SurrealDB/ElevenLabs/Bedrock adapters, dashboard and Cartwheel application remain phase deliverables and must not be presented as working.

**Product:** Change-aware adversarial software release testing (Gate) plus retrospective AI decision/event impact analysis (Recall). Gate reads real code and selects attacks; independent oracles prove regressions before human-approved repair. Recall traces recorded historical exposure, audits actual events or executes control/counterfactual replays and proposes human-reviewed remediation.

## Start here

1. Read [`docs/DEVELOPMENT_PLAN.md`](docs/DEVELOPMENT_PLAN.md) and [`docs/DESIGN.md`](docs/DESIGN.md).
2. Read [`AGENTS.md`](AGENTS.md), [`CONTRIBUTING.md`](CONTRIBUTING.md), [`docs/OWNERSHIP.md`](docs/OWNERSHIP.md), [`docs/PHASES.md`](docs/PHASES.md).
3. Choose owner A/B/C and start at **Phase 0**. Read the named owner handoff in [`docs/AGENT_HANDOFFS.md`](docs/AGENT_HANDOFFS.md).
4. Review actual provider capabilities in [`docs/SDK_VALIDATION.md`](docs/SDK_VALIDATION.md). No credentials in commits or test logs.

## Architecture

```text
Git / PR ──> Change intelligence ──> Gate planner ──> Attack workers
                 │                                      │
         SurrealDB Agent Memory                   Daytona + Anchor
                 │                                      │
              Recall <──── lineage / history      Independent oracle
                 │                                      │
            Counterfactual <──── shared replay / evidence ──> Arize
                 └──────────────> Human review / dashboard
```

A owns contracts, domain, Gate/Recall orchestration and code analysis. B owns workers, sandbox/replay, trusted oracles, providers, storage and memory. C owns the demo target, UI, thin API/composition, root tooling and written guides. Root and cross-team contract changes need all-three review.

## Offline scaffold check

Requirements: Python 3.12+, `pydantic>=2`, `fastapi`, `pytest`, and (for HTTP tests) `httpx`.

```bash
PYTHONPATH=services/gauntlet/src python -m pytest -q services/gauntlet/tests
PYTHONPATH=services/gauntlet/src python -c "from gauntlet.api.main import app; print(app.title)"
```

The scaffold routes only `/health` and does not create provider resources. After installing `uv` and producing a real `uv.lock`, use `uv sync --all-extras` and `uv run pytest`. For frontend work, initialize the two `apps/*` packages and generate/commit `pnpm-lock.yaml` before running `pnpm install --frozen-lockfile`. Missing apps **must not** be treated as successful build steps.

## Secrets and external services

Copy `.env.example` to `.env.local` (gitignored) and populate only the credentials needed for the current verified integration. **No real payments, production targets, or personal customer data.** Use approved test repos and synthetic data. External smoke calls require explicit opt-in; offline tests never call vendors.

## First deliverable

All three owners agree on `AttackSpec`, `ReplaySpec`, `RecallVerdict`, `RunEvent` and golden files; B proves one fake-worker oracle; C serves a simple run event, then integrate a real UI PR. The release gate is a **review recommendation**, not an automated merge or deploy.
