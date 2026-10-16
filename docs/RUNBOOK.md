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

Approved 2026-10-16 (owner decision): `cryptography==50.0.2` in the `live-providers`
group, used only for GitHub App RS256 JWT signing and imported lazily; without it the
GitHub App adapter raises "missing cryptography" and its tests skip.

Not yet approved: `surrealdb`/`surrealdb[memory]` (the memory extra is a prerelease that needs a separately resolved lock), `arize`/`arize-otel`, ElevenLabs. Each needs its own owner proposal. New packages need A/B/C review per CONTRIBUTING.

Dashboard: `pnpm audit --prod` found four postcss advisories (two high, two moderate) bundled by Next 15.5.28, the latest 15.x. A root `pnpm.overrides` entry forces `postcss>=8.5.23`; typecheck, lint, tests and build pass and the audit is clean. Revisit when Next ships a patched dependency.

## P1 credential loading and readiness

The probe scripts read the process environment; they do not automatically load
`.env.local`. Keep credentials in a private, gitignored file. Never paste keys
into command arguments or commit them. For the pinned optional provider environment,
load that file without shell evaluation using the installed dotenv module:

```bash
uv sync --frozen --group live-providers
.venv/bin/python -m dotenv -f .env.local run --no-override -- .venv/bin/python scripts/probe_b01_provider_smoke.py
```

This command performs local preflight only. It does not create resources, validate
keys, or authorize spend. Existing process variables take precedence. Provider
execution additionally requires `RUN_LIVE_INTEGRATIONS=1`, `--execute`,
`--authorize-spend`, and a validated `--registration` file.

For the current P1 smoke, configure `DAYTONA_API_KEY`, `DAYTONA_API_URL`,
`DAYTONA_TARGET`, `ANCHOR_API_KEY`, and `ANCHOR_PROXY_SERVER`,
`ANCHOR_PROXY_USERNAME`, `ANCHOR_PROXY_PASSWORD`. Allow `cartwheel-fixture` in
`GAUNTLET_ALLOWED_TARGET_IDS`. Registration must identify the exact committed
base/head source revisions, registered snapshots, equivalent pinned image digest,
fixture IDs/checksums/state path, repository path, preview port/domain and readiness
path. Snapshots must already serve their separately compiled synthetic fixture.
An ordinary proxy credential does not establish the required egress policy.

The committed Cartwheel baseline includes `fixture-state.json` in both generated
revisions. After creating the two private Daytona snapshots, prepare an
untracked registration file with the actual provider values:

```bash
.venv/bin/python scripts/prepare_cartwheel_registration.py \
  --base-snapshot <actual-base-snapshot> \
  --head-snapshot <actual-head-snapshot> \
  --image-digest <common-64-character-image-digest> \
  --repo-path /workspace/cartwheel \
  --preview-domain-suffix .daytonaproxy01.net \
  --preview-port 3000 \
  --output /tmp/cartwheel-registration.json
```

Replace the sample path, suffix and port with those of the actual snapshots.
The command derives the committed SHA/checksum and state digest, validates the
registration format, and refuses to overwrite an existing file. It does not
create or inspect snapshots. The provider smoke now checks `/api/build-info`
over each signed preview for the exact selected SHA before any browser action.
That synthetic receipt does not attest the sandbox image. Keep the registration
file outside Git and restrict its access to the operator.

Bedrock planning separately requires AWS credentials through a profile/role or
credential environment variables, model access, and explicit `--model-id` and
`--region` arguments. `BEDROCK_MODEL_ID` and `AWS_REGION` in the example file are
operator configuration references; the CLI does not translate them into arguments.
Also pass an authorized `--repository`, `--change-request`, unused writable
`--output`, and the same explicit live/spend switches. Run the CLI without
arguments for its safe missing-input report.

Full source mypy validation currently requires the optional provider SDKs installed
via `uv sync --frozen --group live-providers`. The default CI environment runs
API-only mypy and the full offline test suite without those SDKs.

## Execute a frozen plan locally

The Bedrock probe writes a report containing `frozen_plan`. The local execution
probe accepts that nested object as a **bare receipt file**, not the whole report.
Extract it without altering its fields, for example:

```python
import json
from pathlib import Path
report = json.loads(Path("model-report.json").read_text())
with Path("plan-receipt.json").open("x") as receipt:
    json.dump(report["frozen_plan"], receipt)
```

Use `scripts/probe_p1_frozen_gate.py --help` for arguments. Select `base` or `head`,
provide the receipt, existing Chrome executable, generated fixture repo, loopback
origin and a new output directory. Supply `--expected-change` (trusted
ChangeRequest JSON), `--expected-plan-hash`, `--expected-model-id`,
`--expected-prompt-sha256`, and `--expected-run-id` from the independently reviewed
planning record. Do not infer the expected values from an untrusted receipt; its
hash is not a signature. The prompt hash is SHA-256 of the exact instruction text
passed to the planner, encoded as UTF-8.

Build and start each selected fixture revision separately. The consumer verifies
both checkout SHA and compiled receipt before Chrome starts, enforces supported
UI/oracle and execution budgets, then runs each unchanged attack twice. Repeat
with the same receipt/expected identity on the other revision. Reports include
actual observations and oracle outcomes, without asserting which revision should
fail. A single-revision report is not a paired Gate finding: `gate_status` remains
`not_tested` pending independent attribution. Empty or rejected plans do not run.

For the scripted local diagnostic, run `scripts/probe_p1_local_gate.py` once on
each separately built Cartwheel revision with the same explicit `--run-id` and
fresh output directories. Its stdout includes the SHA-256 of each saved report.
Then run `scripts/probe_p1_paired_gate.py` with the independently noted run ID,
plan hash, both report hashes, both output directories, and the generated
fixture repository. The paired consumer re-freezes the plan, reloads every
stored artifact, and recomputes the hard browser oracle before attribution.
Its `local_pair_status` describes the diagnostic; top-level `gate_status`
remains `not_tested` because this path has a scripted proposal and only a local
Cartwheel build receipt for server provenance.

The 2026-10-16 headless Chrome check on generated revisions
`ad74b08a77ceb1d9452d4335261c99c1db7376e9` and
`fd32708bcd615e072327c0771f49c69329e123e3` produced two base passes and
two head failures under the same plan hash
`b4e27820046f163f71b45924708aa9359db519d7c53f4d9d4efebec469d7bca0`.
The paired report is `/tmp/gauntlet-a01f-paired-report.json`. It labels the
local result `confirmed_regression` with `introduced` attribution and keeps the
product Gate status `not_tested`. No Daytona or Anchor resource was used.

For the unrelated clean Cartwheel change, build a separate checkout with
`scripts/build_cartwheel_clean_fixture.py --dest <new-directory>`. Its clean SHA
is `27548050633077b5d865431fd736fb9b92a28085`; only the product description
page differs from base. Run the local probe with `--clean-sha` on both base and
clean checkouts, using the same run ID and separately built servers. Pass the
same `--clean-sha` and both report hashes to the paired consumer. The 2026-10-16
headless Chrome run produced two base passes and two clean passes under plan hash
`92b2cae9813a9a0799e3ff0fc67382c63a564fe3cfa9833708ba0ac5bdfb10f8`.
The independent report `/tmp/gauntlet-a01g-paired-report.json` records
`local_pair_status=passed`, zero failures and `gate_status=not_tested`. This is
a scripted local false-positive check; it is not a blind Bedrock or Anchor run.

## Demo API and dashboard (Session 3, 2026-10-16)

```bash
export GAUNTLET_REVIEWER_TOKENS='demo-reviewer:<16+ char token>'   # dev-grade login only
uv run uvicorn gauntlet.api.main:app --port 8000
pnpm --filter @gauntlet/dashboard build && (cd apps/dashboard && npx next start -p 3000)
```

- `POST /gate/runs {"change_id": "help-button" | "clean" | "refund-tool"}` runs Session 1's
  `RunGateUseCase`. Adapter choice: Daytona + Anchor only with `RUN_LIVE_INTEGRATIONS=1` and all
  their keys; else local Chromium if `CARTWHEEL_BASE_ORIGIN`/`CARTWHEEL_HEAD_ORIGIN` are set
  (Help-button only, needs `--group live-providers`); else offline fake sandbox + simulated
  layout. `refund-tool` runs the AI-agent route (fixture tool code per revision in the local
  tool world, ledger oracle). `GET /gate/runs/{id}/check-run` previews the GitHub check run;
  `GET /onboarding` lists registered targets and open operator steps.
- `/recall/*` runs Session 1's `RunRecallUseCase` over `apps/cartwheel/history` (checksum
  verified). `/approvals` records hash-bound A-03 approvals; identity comes only from the bearer
  token table. Remediation approvals are review-only.
- Runs, artifacts and approvals live in API process memory; restarting clears them.
- After changing API routes: `uv run python scripts/export_openapi.py` then
  `pnpm --filter @gauntlet/dashboard generate:api`.
- Rehearsal: `uv run --frozen --group live-providers python scripts/demo_rehearsal.py
  [--backup-dir artifacts/demo-backup]` drives the DEMO.md click-path offline in Chromium and
  asserts every step; with `--backup-dir` it saves screenshots, JSON and an `index.html`
  playback page. CI job `demo-rehearsal` runs it and uploads the backup.
- The dashboard reads `GAUNTLET_API_URL` at runtime (server side); `NEXT_PUBLIC_GAUNTLET_API_URL`
  is fixed at build time.
- Demo click-path, go-live checklist and fallback: `docs/DEMO.md`.

## Core engine commands (Session 1)

All default to offline adapters and print JSON with an `adapters` block. Offline labels
mean no provider was contacted.

| What | Command | Expected offline result |
|---|---|---|
| Gate, Help button | `uv run python scripts/run_gate.py` | `confirmed_regression`, head 2/2, base 0/2 |
| Gate, unrelated change | `uv run python scripts/run_gate.py --clean` | `passed` |
| Gate + accessibility worker | `uv run python scripts/run_gate.py --a11y` | both attacks `confirmed_regression` |
| Gate, AI refund tool (P2) | `uv run python scripts/run_gate.py --change refund-tool` | `confirmed_regression` (needs `node`) |
| Repair (P3), step 1 | `uv run python scripts/run_repair.py --run-id demo-1` | prints `plan_sha256` + diff |
| Repair, step 2 | `GAUNTLET_REVIEWER_TOKENS=alice:<16+ chars> GAUNTLET_REVIEWER_TOKEN=<same> uv run python scripts/run_repair.py --run-id demo-1 --approve-hash <sha256>` | `fix_verified_review_required` |
| Memory (P7) | `run_gate.py --memory local --learn`, then `run_gate.py --clean --memory local` | second plan cites the fact |
| Recall (P4–P6) | `uv run python scripts/run_recall.py` | 3 tainted, 2 cleared, 1 not_replayable; audit 3 violations |

Real browser, no cloud: build base/head with `scripts/build_cartwheel_fixture.py`, run
`npx next build && npx next start -p 3101|3102 -H 127.0.0.1` in clean checkouts (exclude
`package-lock.json` via `.git/info/exclude`), then
`CARTWHEEL_BASE_ORIGIN=http://127.0.0.1:3101 CARTWHEEL_HEAD_ORIGIN=http://127.0.0.1:3102 uv run --group live-providers python scripts/run_gate.py --sandbox local --browser local`.

Live (needs keys + `RUN_LIVE_INTEGRATIONS=1`): `--model azure`, `--sandbox daytona --browser anchor`
(`GAUNTLET_DAYTONA_REGISTRATION`, `GAUNTLET_ANCHOR_REQUIRE_PROXY=0`), `--memory surreal`,
`run_recall.py --model azure`. See `docs/SDK_VALIDATION.md`; all are NOT RUN so far.
