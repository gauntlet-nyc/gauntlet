# Developer/operator runbook

## Before start

Python 3.12+, `uv`, Node >=22, pnpm, Docker and Git recommended. Copy `.env.example` to `.env.local` and privately fill only the required provider keys. First prove offline contracts and pure tests before any paid calls. Local scripts MUST NOT invoke real provider endpoints unless `RUN_LIVE_INTEGRATIONS=1` and explicit operator consent.

## Dev environment (worktree bootstrap)

Use the worktree-local `.venv`; never install dependencies globally. On B-00,
Python 3.14 and uv 0.11.28 were used (project requirement: Python 3.12+).
The existing root dependency groups define the offline tools. Until C's lockfile
is integrated, a fresh worktree can bootstrap without writing a competing lock:

```bash
uv venv .venv
uv pip install --python .venv/bin/python -e services/gauntlet --group dev
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy services/gauntlet/src
uv build --package gauntlet-control --out-dir /tmp/gauntlet-build
```

After the approved `uv.lock` lands, use `uv sync --frozen` instead of the unlocked
bootstrap above. Provider SDKs are not part of B-00's offline environment; C owns
dependency/lock changes. `scripts/probe_sdk_inventory.py` reports installed and
optional published versions without calling provider services or reading keys.
For local headless diagnostics, Node 22+ and an existing Chrome executable are
required; see `docs/SDK_VALIDATION.md`. This probe adds no npm dependency.
The generated Cartwheel fixture is a separate project without a committed Node
lockfile or `packageManager` field. In that generated temporary checkout, run
`npm install --no-package-lock --ignore-scripts`, then `npm run build` and
`./node_modules/.bin/next start -p 3100` for the local probe. Keep these
installed packages and build outputs outside the tracked fixture templates;
Corepack may otherwise try to add its own package-manager version there.

## Offline check (implemented scaffold)

```bash
PYTHONPATH=services/gauntlet/src python -m pytest -q services/gauntlet/tests
PYTHONPATH=services/gauntlet/src python -c 'from gauntlet.api.main import app; print(app.title)'
```

## Post-bootstrap target sequence (to implement in phases)

1. Initialize `uv.lock`, `pnpm-lock.yaml` and pinned Compose images; prove `uv run pytest`, `pnpm -r typecheck`.
2. Start local SurrealDB core and synthetic Postgres; apply reviewed migrations with no production URLs.
3. Start Cartwheel web/API, control API and dashboard. `GET /health` is local API only; target app gets separate `/health` and fixture checksum.
4. Run Daytona/Anchor smoke (owned preview access only) and Arize span insertion; verify output in provider consoles.
5. Seed deterministic base/head fixtures, confirm checksums match, run Gate UI and AI suites; repeat after patch.
6. Seed historical synthetic decisions/lineage; run Recall event audit and counterfactual; inspect incompletes.
7. Rebuild proof bundle; check that evidence paths/trace IDs really exist and secret scanner is clean.

## Resets and failures

A demo reset should only delete **scoped synthetic** state for a known `fixture_id`, never issue broad delete commands. If provider unavailable: flag `environment_error` or use an explicit offline recorded demo with label. If browser cannot see localhost, use validated Daytona signed previews. If ReplaySpec hash mismatches historical content: mark `not_replayable`. If orchestration fails partway, teardown browser and sandbox and persist failed job event. Never silently retry a non-idempotent refund action.

## Operational support

Log UTC/run_id/attempt_id/replay_id/trace_id for every attempt. Track sandbox leaked resources, token spend and browser session TTL. Keep artifacts restricted; rotate leaked keys; do not store raw historical customer content in Arize traces.

## Approved provider dependencies (C, 2026-10-14)

Approved and pinned for B-01a only, in the non-default dependency group `live-providers` (root `pyproject.toml`, resolved in `uv.lock`): `daytona==0.224.1`, `anchorbrowser==1.0.1`, `playwright==1.64.0`, and `boto3==1.43.114` (A-01c planning probe). Default `uv sync` and CI do not install them; use `uv sync --frozen --group live-providers`. Checked: PyPI publisher metadata matches the vendors, none are yanked, and `pip-audit` on the resolved set reported no known vulnerabilities. Approval is for installing and signature checking only. Live calls still need `RUN_LIVE_INTEGRATIONS=1`, explicit spend authorization and an approved synthetic target. `playwright install` (browser download) is not part of this approval.

Not yet approved: `surrealdb`/`surrealdb[memory]` (the memory extra is a prerelease that needs a separately resolved lock), `arize`/`arize-otel`, `boto3`, ElevenLabs. Each needs its own owner proposal. New packages need A/B/C review per CONTRIBUTING.

Dashboard: `pnpm audit --prod` found four postcss advisories (two high, two moderate) bundled by Next 15.5.28, the latest 15.x. A root `pnpm.overrides` entry forces `postcss>=8.5.23`; typecheck, lint, tests and build pass and the audit is clean. Revisit when Next ships a patched dependency.
