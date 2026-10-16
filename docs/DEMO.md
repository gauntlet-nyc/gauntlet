# 3:30 PM demo — click-path, talk track, go-live checklist, fallback

This is the exact script for the submitted demo. Every screen shows an **OFFLINE / live NOT RUN**
badge when any of its data came from fakes, recordings or fixtures. Never talk over that badge:
say out loud which parts are live. `not_tested` never means safe.

## 0. Start (5 minutes before)

```bash
# Terminal 1 — API (reads env vars only through gauntlet/settings.py and api/settings.py)
export GAUNTLET_REVIEWER_TOKENS='demo-reviewer:<a 16+ char token you choose>'
export GAUNTLET_ANCHOR_REQUIRE_PROXY=0          # weaker isolation, see docs/SECURITY.md
uv run uvicorn gauntlet.api.main:app --port 8000

# Terminal 2 — dashboard
pnpm --filter @gauntlet/dashboard build
cd apps/dashboard && npx next start -p 3000      # NEXT_PUBLIC_GAUNTLET_API_URL defaults to :8000
```

Open `http://localhost:3000/sponsors` first and read the table: it lists every sponsor, the
missing env var *names* and "offline-tested, live NOT RUN" until a recorded live run exists.
Then go to `/login` and paste the reviewer token (kept in an httpOnly cookie; demo-grade only).

## 1. Act A — Gate on the Help-button PR (≈90 s)

| Click | Show | Say |
|---|---|---|
| **Gate** → change "Add a floating Help button" → **Start Gate run** | Run page | "CI is green. Nobody wrote a test for small screens. Gauntlet reads the diff and writes one." |
| Scroll to **Diff** | `FloatingHelp.module.css`: `position: fixed; bottom: 16px` | "The planner cites these exact lines." |
| **Frozen plan** | Plan hash, attack `attack-ui-primary-action-375`, steps navigate → resize 375×812 → click Checkout | "The plan is hashed and frozen *before* anything runs. The model only proposes; it can't run shell or change the oracle." |
| **Attempts: head vs base** | head 2/2 fail ("Another element intercepted the click"), base 0/2 | "Same attack, twice on each side, in separate environments. Base passes, head fails." |
| **Verdict** | `confirmed regression — introduced by this PR` | "That's attribution: this PR introduced it, it wasn't already there." |
| **Screenshots** | evidence images per attempt | "Evidence is stored write-once and the oracle re-checks the bytes." |
| **Fix plan review** → **Approve fix plan** | Banner: bound to plan hash, nothing merged | "A human approves this exact hash. Change one byte and the approval is void. Nothing auto-merges." |
| **Events** | `plan_frozen` before `environments_ready`, `approval_recorded` last | |
| **▶ Play voice briefing** | Spoken summary | "Briefing is built from stored findings only. Voice can't approve anything." |

Optional false-positive check: start **"Clarify the product description"** → `passed` on both
sides. Start **"Let the support assistant request refunds"** → `not_tested` (AI/tool worker not
routed yet): "Not tested does not mean safe."

## 2. Act C — Recall on the refund agent (≈90 s)

| Click | Show | Say |
|---|---|---|
| **Recall** | Event audit: 36 audited, 3 violations, 1 inconclusive, 32 clear | "History alone is an *audit*. A violation needs the ledger to show money credited to a non-owner — a caller mismatch alone never counts." |
| inconclusive card `tool-event-007` | "tool outcome was not recorded" | "Missing logs are inconclusive, never clear." |
| **Counterfactual — trigger kb-117** | 3 tainted, 2 cleared, 1 not replayable | "We replay each exposed decision: control first, with every input pinned. It must reproduce the original. Then remove only kb-117." |
| card `decision-009` | path `kb-117 → derived_into → mem-083 → read_by → decision-009` | "Second-order: the bad KB chunk became a memory note, and a later decision read it." |
| card `decision-004` | cleared | "Exposed, but the owner would have been refunded anyway. Exposure is not harm." |
| card `decision-007` | not replayable, missing `tool_results_hash` | |
| **Review queue** → **Approve for review** on `reverse_transaction_review` | Banner | "Review only. Nothing is reversed, refunded or sent to a customer." |

## 3. Close (≈30 s) — **Sponsor proof**

Read each row honestly: which artifact each sponsor produces and whether it ran live today.
Pitch: "CI passed because no one wrote the test. Gauntlet read what changed, invented the test,
proved the failure in isolation and gated the fix on a human. When the bug already shipped,
Recall separates documented harm from assumptions."

## Morning go-live checklist

Set keys in a private, gitignored `.env.local` (template: `.env.example`), load with
`.venv/bin/python -m dotenv -f .env.local run --no-override -- <command>`, and never paste keys
into commands. First run `uv run python scripts/check_settings.py` — it prints only names.

| Sponsor | Env vars to set | Command that proves it live | Then |
|---|---|---|---|
| Azure OpenAI (planner) | `GAUNTLET_MODEL_PROVIDER=azure`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_KEY`, `RUN_LIVE_INTEGRATIONS=1` | `RUN_LIVE_INTEGRATIONS=1 uv run python scripts/run_gate.py --model azure` | report `adapters.model = live_azure_openai`, plan accepted by the validator |
| Daytona | `DAYTONA_API_KEY`, `DAYTONA_API_URL`, `DAYTONA_TARGET`, `GAUNTLET_DAYTONA_REGISTRATION` (file from `scripts/prepare_cartwheel_registration.py`) | with Anchor below: `RUN_LIVE_INTEGRATIONS=1 GAUNTLET_ANCHOR_REQUIRE_PROXY=0 uv run --group live-providers python scripts/run_gate.py --model azure --sandbox daytona --browser anchor` | provider console shows base/head sandboxes; report `sandbox = live_daytona` |
| Anchor | `ANCHOR_API_KEY`, `GAUNTLET_ANCHOR_REQUIRE_PROXY=0` (or the `ANCHOR_PROXY_*` trio with `=1`) | same command as Daytona | `browser = live_anchor_no_egress_proxy`; recording in Anchor console |
| Arize AX | `ARIZE_API_KEY`, `ARIZE_SPACE_ID`, `ARIZE_PROJECT_NAME` | see the Arize row in `docs/SDK_VALIDATION.md` | correlated spans visible in AX |
| SurrealDB core | `SURREAL_URL`, `SURREAL_NS`, `SURREAL_DB`, `SURREAL_USER`, `SURREAL_PASS` | see the SurrealDB row in `docs/SDK_VALIDATION.md` | records visible in Surrealist |
| SurrealDB Agent Memory | `SURREAL_MEMORY_ENDPOINT`, `SURREAL_MEMORY_CONTEXT`, `SURREAL_MEMORY_API_KEY` | see the Agent Memory row in `docs/SDK_VALIDATION.md` | `remember`/`recall as_of` round-trip |
| ElevenLabs | `ELEVENLABS_API_KEY`, `ELEVENLABS_AGENT_ID`, `VOICE_WEBHOOK_SECRET` | see the ElevenLabs row in `docs/SDK_VALIDATION.md` | briefing spoken by the agent |
| Recall with a model | Azure vars above | `RUN_LIVE_INTEGRATIONS=1 uv run python scripts/run_recall.py --model azure` | control replays must still match; any mismatch shows as inconclusive |

After a sponsor's command really succeeds: record date, version, command and sanitized result
in `docs/SDK_VALIDATION.md`, then (and only then) change that sponsor's row in
`services/gauntlet/src/gauntlet/api/services/sponsors.py` to "live verified". Setting env vars
alone never changes the panel. Restart the API after changing env vars (settings are read once).

With `RUN_LIVE_INTEGRATIONS=1` and keys set, the same **Start Gate run** button uses the live
planner/Daytona/Anchor; the provenance list on the run page names every adapter that ran.

## Fallback if a live service fails on stage

1. **Do not retry blindly.** Say which provider failed. A failed run shows `not_tested` with the
   reason; that is the honest result.
2. **Real local browser (no sponsors):** build and serve the fixture locally (RUNBOOK →
   "Execute a frozen plan locally"), then restart the API with
   `CARTWHEEL_BASE_ORIGIN=http://127.0.0.1:3101 CARTWHEEL_HEAD_ORIGIN=http://127.0.0.1:3102`
   and `uv run --group live-providers uvicorn gauntlet.api.main:app --port 8000`. The Help-button
   run then uses real headless Chromium; provenance says "Local headless Chromium (not Anchor)".
3. **Fully offline:** unset `RUN_LIVE_INTEGRATIONS`. Gate runs the scripted planner, fake
   sandbox and simulated layout browser through the real oracle path; Recall runs the
   deterministic synthetic agent replay. Every page shows **OFFLINE / live NOT RUN**.
4. **Recorded run from the morning:** if a live run succeeded earlier, show its saved report
   (`artifacts/gate-runs/<run_id>/`) and provider console screenshots, and say they are
   recordings with their timestamp.

## Q&A notes

Playwright runs scripts; Gauntlet proposes tests from the diff and verifies them with trusted
oracles. Historical logs alone are an event audit, not a counterfactual. Daytona gives isolated
comparable worlds; Anchor drives the real cloud browser; Arize shows traces/evals but is never the
oracle; SurrealDB Agent Memory stores typed provenance over time; ElevenLabs only reads findings
aloud. Targets are synthetic. The Anchor proxy is off for this demo (weaker isolation, flagged in
the provenance). Reviewer login is dev-grade.
