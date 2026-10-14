# Developer/operator runbook

## Before start

Python 3.12+, `uv`, Node >=22, pnpm, Docker and Git recommended. Copy `.env.example` to `.env.local` and privately fill only the required provider keys. First prove offline contracts and pure tests before any paid calls. Local scripts MUST NOT invoke real provider endpoints unless `RUN_LIVE_INTEGRATIONS=1` and explicit operator consent.

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

## Reviewer tokens (dev)

Approval routes (`POST /v1/fix-plans/{id}/approve`) accept only a bearer token found in the server-side table `GAUNTLET_REVIEWER_TOKENS`, a JSON object like `{"<token>": {"reviewer_id": "rev-1", "channel": "dashboard"}}`. Unset means every approval is refused. The dashboard server reads one token from `GAUNTLET_REVIEWER_TOKEN` (not `NEXT_PUBLIC_*`). This is development-grade auth pending a real identity provider decision; approval state is in memory and lost on restart.
