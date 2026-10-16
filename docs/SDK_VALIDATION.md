# SDK integration validation checklist — B owns

**Starter baseline; see dated updates below for current results.** Record installed SDK version, exact API call, invocation environment, sanitized output/trace ID, elapsed time, cleanup result and SDK doc URL. Never commit keys. Package APIs and feature entitlements may change.

| Provider | Required live smoke | Known docs | Recorded result |
|---|---|---|---|
| Daytona | create sandbox, execute, access preview, optionally eligible VM fork, destroy | https://www.daytona.io/docs/en/python-sdk/ | 2026-10-16 cold restore and signed preview receipts PASSED; VM fork not tested |
| Anchor | create cloud session, resize, inspect, click approved preview, capture recording, close | https://github.com/anchorbrowser/AnchorBrowser-SDK-Python | NOT RUN |
| Arize AX | `arize.otel.register`, correlated span visible in AX, one actual evaluated experiment | https://arize.com/docs/ax/quickstarts/quickstart-write-first-eval | NOT RUN |
| SurrealDB core | AsyncSurreal connect, param insert/query, relation, update and close | https://surrealdb.com/docs/reference/python/api/core/surreal | NOT RUN |
| SurrealDB Agent Memory | separate context `remember`, `recall` and `as_of`/provenance query | https://surrealdb.com/docs/agent-memory/integrations/sdks/python | NOT RUN |
| AWS Bedrock | invoke approved configured model with bounded tool/JSON output | https://docs.aws.amazon.com/boto3/latest/reference/services/bedrock-runtime/client/converse.html | NOT RUN |
| ElevenLabs | authenticated evidence webhook call and private-voice conversation | https://elevenlabs.io/docs/eleven-agents/libraries/python | NOT RUN |

**SDK notes:** Daytona's VM sandbox supports `fork()`; container sandboxes require snapshot/recreation. Agent Memory is prerelease and separate from core SurrealDB DB SDK. Bedrock model IDs/availability vary by region/account. Anchor browser runs in cloud and cannot reach localhost without approved preview/tunnel. Arize is evaluation visibility, not the trusted oracle.

**Record format:** `Date / owner / provider / pinned version / test SHA / command (no tokens) / raw sanitized result / failure / fallback / next verification`.

## Session 2 adapter status (2026-10-16) — offline-tested, live NOT RUN

Keys were not available. Every row below is **offline-tested, live NOT RUN** until an
operator runs the listed command with real keys and records the result here. All settings
come from `gauntlet.settings.load_settings()`; check readiness (names only, no values) with
`uv run python scripts/check_settings.py`.

| Adapter | Offline tests | Live status | Exact live command |
|---|---|---|---|
| Settings module | `tests/test_s2_settings.py` | n/a | `uv run python scripts/check_settings.py` |
| Go-live check (`scripts/go_live_check.py`, `execution/go_live*.py`) | `tests/test_s2_go_live.py` | probes are connectivity checks, not sponsor runs. SurrealDB core probe ran against local SurrealDB 2026-10-16 (`probe ok`); all hosted probes NOT RUN | `RUN_LIVE_INTEGRATIONS=1 .venv/bin/python -m dotenv -f .env.local run --no-override -- .venv/bin/python scripts/go_live_check.py --probe` |
| Anchor without egress proxy (`GAUNTLET_ANCHOR_REQUIRE_PROXY=0`) | `tests/test_s2_settings.py` | live NOT RUN | `RUN_LIVE_INTEGRATIONS=1 GAUNTLET_ANCHOR_REQUIRE_PROXY=0 .venv/bin/python -m dotenv -f .env.local run --no-override -- .venv/bin/python scripts/probe_b01_provider_smoke.py --registration /tmp/cartwheel-registration.json --execute --authorize-spend` |
| SurrealDB core run store + lineage/history (`persistence/surreal_store.py`, HTTP `/rpc`, httpx) | `tests/test_s2_surreal_core.py` (offline transport) | **local SurrealDB v2.3.7 RUN 2026-10-16** (pinned compose image, in-memory): append-only, sequence/idempotency conflicts, concurrent append, lineage edges, decision/tool-event window all passed; hosted live NOT RUN | `RUN_LIVE_INTEGRATIONS=1 .venv/bin/python -m dotenv -f .env.local run --no-override -- .venv/bin/python scripts/smoke_surreal.py` |
| SurrealDB **Agent Memory SDK** (`memory/agent_memory_sdk.py`, `surrealdb[memory]==3.0.0b10` + `surrealdb-memory==1.0.0b1`, owner-approved prerelease, `live-providers`) | `tests/test_s2_agent_memory_sdk.py` (real SDK `AsyncMemory` with an injected fake transport: `POST …/facts`, `POST …/query`; encoding, as-of, supersession, lens) | live NOT RUN. Signatures read from the installed 3.0.0b10 package on 2026-10-16. `persistence.factory.memory_store` prefers the SDK and falls back to the HTTP context below (`GAUNTLET_MEMORY_BACKEND=sdk\|http`) | `RUN_LIVE_INTEGRATIONS=1 .venv/bin/python -m dotenv -f .env.local run --no-override -- uv run --group live-providers python scripts/smoke_surreal.py --memory` (report shows `memory_backend`) |
| Temporal memory on a separate SurrealDB memory context (`memory/surreal_memory.py`) | `tests/test_s2_memory.py` | **local SurrealDB RUN 2026-10-16**: provenance, as-of (no hindsight), supersession history, lens filtering passed. SurrealDB **Agent Memory product SDK not used** (`surrealdb[memory]` not approved); Agent Memory live NOT RUN | `RUN_LIVE_INTEGRATIONS=1 .venv/bin/python -m dotenv -f .env.local run --no-override -- .venv/bin/python scripts/smoke_surreal.py --memory` |
| Arize OTLP tracing (`integrations/arize/`: planner LLM, worker, oracle, replay wrappers; hand-encoded OTLP protobuf over httpx) | `tests/test_s2_arize.py` (protobuf decoded and checked) | **hosted live smoke PASSED 2026-10-16**: six synthetic spans exported, zero dropped; trace `a5ea7c463ede5060e39de13ed56a7add`. This verifies ingestion, not a real Gate run. | `ELEVENLABS_API_KEY= VOICE_WEBHOOK_SECRET= RUN_LIVE_INTEGRATIONS=1 .venv/bin/python -m dotenv -f .env.local run --no-override -- .venv/bin/python scripts/smoke_adapters.py arize` |
| Arize **Experiments SDK** (`integrations/arize/experiments_sdk.py`, `arize==8.59.1`, `live-providers`): one run per replayed decision, verdict as evaluator label | `tests/test_s2_arize_experiments_sdk.py` (real SDK field types, fake client) | **hosted live smoke PASSED 2026-10-16**: synthetic experiment `RXhwZXJpbWVudDoxNjIyNDE6WmQ3MQ==` created with SDK 8.59.1. No real Recall run was published. | Same bounded Arize smoke command above (report shows `arize_experiment_id`) |
| Arize experiments as tagged traces (Recall control vs counterfactual) | `tests/test_s2_arize.py` | **hosted synthetic trace exported 2026-10-16**: experiment trace `597e8ca7550e6028497dd4df5aebe7b9`. The separate Experiments SDK is also approved and smoke tested above. | Same bounded Arize smoke command above |
| Daytona clean revision (`provision_cartwheel_snapshots.py --include-clean`, `prepare_cartwheel_registration.py --clean-snapshot`) | `tests/test_s2_clean_snapshot.py` (real rebuild reproduces clean SHA `2754805…`; 3-sandbox lifecycle with fakes) | base/head cold restore PASSED earlier (see below); clean snapshot live NOT RUN | `RUN_LIVE_INTEGRATIONS=1 GAUNTLET_ALLOWED_TARGET_IDS=cartwheel-fixture .venv/bin/python -m dotenv -f .env.local run --no-override -- .venv/bin/python -m scripts.provision_cartwheel_snapshots --lockfile <reviewed-linux-lock> --image node:22-bookworm@sha256:0e5f906573693feaa1e21057ebdcfdb5bd5021f050b2dc7c9deceb629c7da2a8 --preview-domain-suffix <suffix> --output /tmp/cartwheel-registration.json --include-clean --execute --authorize-spend` (omit `--execute --authorize-spend` for the no-spend dry run) |
| P10 job/cost ledger + resource leases (`persistence/jobs.py`) | `tests/test_s2_jobs_retention.py` (offline + local) | **local SurrealDB RUN 2026-10-16**: legal transitions only, budget overrun recorded then refused, leaked-lease recovery with failing/unknown cleaners, stale-job interruption passed. Not yet wired into the Gate orchestrator | n/a (uses SurrealDB core settings) |
| P10 evidence retention (`execution/retention.py`) | `tests/test_s2_jobs_retention.py` | local filesystem; dry-run by default, protected evidence kept, symlinks/other files untouched | `sweep_artifacts(root, retention_days=GAUNTLET_EVIDENCE_RETENTION_DAYS, now=..., protected_ids=..., apply=True)` |
| GitHub App check runs (`integrations/github_app.py`: RS256 App JWT signed with `cryptography` → installation token with `checks: write` → create/update check run) | `tests/test_s2_github_voice.py` (JWT signature verified by `openssl dgst -verify`; request sequence asserted) | live NOT RUN (App not created) | `RUN_LIVE_INTEGRATIONS=1 .venv/bin/python -m dotenv -f .env.local run --no-override -- .venv/bin/python scripts/smoke_adapters.py github --repo <owner/name> --sha <40-char head SHA>` |
| GitHub webhook verification (`security/webhooks.py`: HMAC, delivery replay guard, PR → run) | `tests/test_s2_github_voice.py` | live NOT RUN; forward with smee: `npx smee-client --url $GITHUB_WEBHOOK_PROXY_URL --target http://127.0.0.1:8000/<webhook route>` | API route wiring is owned by the API session |
| ElevenLabs (`integrations/elevenlabs.py` signed URL + TTS briefing; `security/webhooks.py` signed tool webhook) | `tests/test_s2_github_voice.py` | live NOT RUN | `RUN_LIVE_INTEGRATIONS=1 .venv/bin/python -m dotenv -f .env.local run --no-override -- .venv/bin/python scripts/smoke_adapters.py elevenlabs` |

Local SurrealDB tests: `docker compose --env-file .env.local -f infra/local/docker-compose.yml up surrealdb`, then
`SURREAL_TEST_URL=ws://127.0.0.1:8001 SURREAL_TEST_PASS=<local pass> uv run pytest -q services/gauntlet/tests/test_s2_surreal_core.py services/gauntlet/tests/test_s2_memory.py`
(loopback only; each test uses a fresh database).

Anchor without the proxy is **weaker isolation**: only the in-browser route guard limits
navigation to the signed preview origin. The runtime logs a WARNING on construction and on
every session, the smoke report records `egress_isolation`, and each capture records
`browser_session` (`anchor_session_id`, `anchor_recording_id`, `egress_isolation`). Proxy
support is unchanged and remains the default.

### Read-only credential checks (2026-10-15)

Using the project `.venv` and values loaded from the gitignored `.env.local`,
an inline Python check constructed the pinned `AsyncDaytona` client and called
`list(ListSandboxesQuery(limit=1), request_timeout=6)`. Daytona 0.224.1
returned an authenticated response with no sandbox in the first page. The
client was closed. This verifies the configured key, API endpoint and target
can make a read request; snapshot creation, execution, preview and deletion
remain untested.

The same read-only check constructed `AsyncAnchorbrowser` with the configured
key. In Anchor 1.0.1, `sessions.list_sessions(limit=1, timeout=8)` returned
`InternalServerError`, while `sessions.get_all_sessions_status(timeout=8)`
returned successfully. The client was closed. This is evidence of API access
through the status endpoint, not of session creation, browser connectivity or
proxy enforcement. No paid resource was created by either check. Credential
values and provider response bodies were not logged.

### P1 paired adjudication, fixture state, and hosted receipt (2026-10-16)

A-01e added pure paired UI adjudication. It requires two complete, distinct
hard-oracle attempts on each revision, matching trusted identities and stored
artifact bindings, before classifying an introduced or pre-existing failure.
No live Gate result is claimed until the execution consumer supplies trusted
paired records and verifies environment provenance.

C-01d added a committed static `fixture-state.json` to both generated Cartwheel
revisions and a local registration-preparation CLI. The current generated base
is `ad74b08a77ceb1d9452d4335261c99c1db7376e9`, head is
`fd32708bcd615e072327c0771f49c69329e123e3`, and template checksum is
`85bb0ff1af85aa76d3cb76bd6c64932237694f90253b96a6f2af68cbc8c9fb19`.
The CLI derives the fixture-state digest and registration identity from these
committed bytes, but cannot prove that operator-supplied snapshots exist.

B-01o made the narrow provider smoke require a registered target and verify
each selected revision's synthetic `/api/build-info` receipt over its signed
preview before opening Anchor. A mismatched receipt stops that browser action
and the environment pair is cleaned. This verifies an app-served SHA claim;
the sandbox image and custom proxy egress policy still need separate proof.

### B-01p Daytona snapshot bootstrap preparation (2026-10-16)

The project-local Daytona 0.224.1 package was inspected without credentials or
provider calls. Its installed signatures expose
`AsyncDaytona.snapshot.create(CreateSnapshotParams(name, image, entrypoint), timeout=...)`,
`AsyncDaytona.create(CreateSandboxFromSnapshotParams(snapshot, domain_allow_list), timeout=...)`,
`AsyncSandbox.fs.upload_file`, `AsyncSandbox.process.exec`, `AsyncSandbox.stop`,
`AsyncSandbox.create_snapshot(name, timeout=...)`, `AsyncDaytona.snapshot.get/delete`,
and `AsyncDaytona.delete(sandbox, wait=True)`. The [official snapshot docs](https://www.daytona.io/docs/en/snapshots/)
say container cold snapshots retain filesystem state and require a stopped
sandbox; the [Python SDK reference](https://www.daytona.io/docs/en/python-sdk/async/async-sandbox/)
documents the snapshot call. The [network policy docs](https://www.daytona.io/docs/en/network-limits/)
document `domain_allow_list` and warn that organization policy can still block
the npm registry.

`scripts/provision_cartwheel_snapshots.py` performs a local preflight against the
committed synthetic manifest, rebuilt base/head SHAs, identical fixture-state
bytes and a trusted, operator-supplied npm lockfile. Its hash is recorded for
reproduction; this is not a supply-chain verification. It accepts only the
tested full Node 22 Bookworm image index
`node:22-bookworm@sha256:0e5f906573693feaa1e21057ebdcfdb5bd5021f050b2dc7c9deceb629c7da2a8`.
On 2026-10-16, a local Docker linux/amd64 run found `/usr/bin/git`,
`/usr/bin/tar` and `/usr/local/bin/npm` in that image. The exact check was
`docker run --rm --pull=never --platform linux/amd64 --network none
--entrypoint /bin/sh <pinned-image> -c 'command -v git && command -v tar &&
command -v npm'` (exit 0). The slim candidate
`node:22-bookworm-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392`
was rejected because it has no `git`; both the bootstrap and later Daytona
attestation require `git rev-parse HEAD`. The optional paid path requires both CLI flags,
`RUN_LIVE_INTEGRATIONS=1`, the Cartwheel target allowlist and Daytona credentials.
It creates one temporary image snapshot with a conditional Next startup
entrypoint, seeds two private revision sandboxes,
stops them, captures cold snapshots and originally checked for an inherited
entrypoint. The live finding below supersedes that assumption.
Temporary sandboxes and image snapshot are deleted; failed runs also delete
revision snapshots. Output is an untracked registration file and sanitized
metadata, including the actual SDK version and lockfile hash. No paid path was
run for B-01p; offline fakes establish call order and cleanup only.

### B-01q local build and blocked-network seed (2026-10-16)

A bounded live Daytona diagnostic using SDK 0.224.1 created, fetched and
deleted the pinned image snapshot, but sandbox creation returned HTTP 400:
`Network access is restricted and cannot be overridden at the sandbox level.
Remove domainAllowList from the request.` No sandbox was created. The B-01q
bootstrap installs dependencies locally in the pinned linux/amd64 Node image
with Docker bridge networking, then runs `npm run build` with Docker networking
disabled and `NEXT_TELEMETRY_DISABLED=1`. For each committed revision it checks
the exact checkout SHA, clean source tree, compiled output and served
`/api/build-info` SHA in a no-network local container. It uploads the built
source tree, `node_modules` and `.next` as compressed tar to a private Daytona
sandbox created with `network_block_all=True` and no `domain_allow_list`.
Remote commands unpack and attest the uploaded tree before stop and snapshot.
The installed SDK defines `auto_delete_interval` in minutes; these temporary
sandboxes use 20 minutes as a fallback while explicit cleanup handles normal
and failed runs. Daytona restore/startup behavior remains unverified.

The external lockfile is operator reviewed, SHA-256 recorded, and must match
the fixture's root dependencies plus approved Next 15.5.28 and Linux x64 GNU
SWC 15.5.28 entries. The SWC entry must carry sha512 integrity. An older
macOS-generated lock lacked this optional Linux dependency and failed local
Docker build when Next attempted to fetch it without network access. Neither
the lockfile check nor its hash is supply-chain verification. No B-01q paid
provider call was made by the coding agent.

The real no-spend local preflight used the reviewed Linux lock at SHA-256
`c0cfffa2614271ec288c3ef7379316f1bbad8b678dcd302ab151e9d23dbff738`.
With the pinned linux/amd64 image it rebuilt base
`ad74b08a77ceb1d9452d4335261c99c1db7376e9` and head
`fd32708bcd615e072327c0771f49c69329e123e3`, including network-disabled
Next builds and both loopback build receipt checks. The command exited 0 and
reported `status=not_tested`, SDK 0.224.1 and missing spend/provider opt-ins;
no Daytona call occurred. The compressed base/head upload bundles measured
138,661,350 and 138,685,600 bytes. The lockfile remains outside Git.

### B-01r seed stage diagnostics (2026-10-16)

An authorized bounded B-01q Daytona run built both revisions locally, created
the runtime snapshot and reached a base snapshot, then returned a sanitized
`RuntimeError` without identifying the failed seed operation. Subsequent
read-only Daytona listing found no Cartwheel snapshots or sandboxes; cleanup
completed. That run did not establish cold restore or preview startup.

The bootstrap now reports fixed stage codes such as `base_upload`,
`base_extract`, `base_source`, `base_state`, `base_clean`, `base_build`,
`base_stop`, `base_snapshot`, and corresponding `head_*` codes. Runtime create
and fetch, sandbox create, output writing and client close also have fixed
codes. Provider exception text, signed origins and credentials remain absent
from the JSON error report. Offline tests exercise a head-stage failure and
verify cleanup; no paid retry was made for B-01r.

### B-01s explicit cold start (2026-10-16)

A bounded Daytona run confirmed the runtime image snapshot retained the
configured entrypoint, while the sandbox-created cold snapshot was `active`
with `entrypoint=null`. Container cold snapshots capture filesystem state; the
bootstrap now accepts exactly that observed metadata and registers the fixed
`cartwheel_next_v1` startup profile. This profile names one SDK-owned command;
registration cannot supply arbitrary shell. Existing registration files without
`startup_profile` must be regenerated from the bootstrap or registration
script. After a restored sandbox's Git SHA
and fixture-state digest match the registered values, the provider starts the
compiled Next build in the background on the validated preview port. It then
obtains the signed preview and waits for `/checkout` readiness. The hosted
`/api/build-info` receipt remains required before Anchor opens a browser.

Daytona SDK 0.224.1 `AsyncProcess.exec(command, cwd, timeout)` documents a
redirected background command for a long-running server. B-01s uses that
method with a constant command template and the registered integer port.
Offline fakes establish ordering and cleanup. At B-01s branch completion, its
live restore and preview remained unverified; the integrated run below resolves
that checkpoint.

Run the local preflight from the repository root with
`uv run --frozen --no-sync --group live-providers python -m scripts.provision_cartwheel_snapshots
--lockfile <reviewed-package-lock-outside-git> --image
node:22-bookworm@sha256:0e5f906573693feaa1e21057ebdcfdb5bd5021f050b2dc7c9deceb629c7da2a8 --preview-domain-suffix
.daytonaproxy01.net --output /tmp/cartwheel-snapshot-registration.json`.
Without `--execute --authorize-spend`, it prints missing prerequisite names and
does not write a registration or call Daytona. Keep the lockfile and output
outside Git; the lockfile is a trusted operator input, and its hash is retained
for audit. The registration output's parent must already exist outside any Git
checkout. The integrated live run below established Daytona acceptance and
restored startup; the full Gate still requires planner and browser validation.

The generated fixture currently has no committed `package-lock.json`, so an
operator must supply a reviewed lockfile matching its `package.json`. A
successful snapshot creation would still be `not_tested` for P1: the installed
SDK cannot by itself prove that restored cold snapshots can start and serve the
selected compiled build. The integrated live check below restored both
snapshots and verified their preview receipts. P1 remains open.

### Integrated Daytona cold restore smoke (2026-10-16)

With explicit live/spend opt-in and Daytona 0.224.1, the bootstrap created two
private Cartwheel cold snapshots from the reviewed Linux lockfile SHA-256
`c0cfffa2614271ec288c3ef7379316f1bbad8b678dcd302ab151e9d23dbff738`
and pinned Node image digest above. Base and head were the manifest SHAs
`ad74b08a77ceb1d9452d4335261c99c1db7376e9` and
`fd32708bcd615e072327c0771f49c69329e123e3`. The local bundles measured
138,652,980 and 138,686,356 bytes. The successful bootstrap reported
`snapshots_created=true`, `restore_smoke_verified=false`, and `gate_status=not_tested`.
The registration is `/tmp/cartwheel-b01s-registration-current-domain-20261016.json`;
the two final snapshots intentionally remain private in Daytona for subsequent
authorized smokes.

The first restore diagnosed a real adapter signature error: installed
`AsyncFileSystem.download_file(self, *args)` rejects `timeout=30`. A base-only
diagnostic confirmed the file existed with the registered SHA-256. The SDK
adapter and fake signature were corrected, then a second restore diagnosed a
registered preview suffix mismatch. The signed origin was an exact HTTPS origin
under `.daytonaproxy01.net`; the registration was regenerated for that suffix.
No signed URL, token or provider exception text was recorded. Both failed
restores deleted their temporary sandboxes with no pending cleanup IDs.

The final invocation was `RUN_LIVE_INTEGRATIONS=1` with the project-local
`python -m dotenv -f <gitignored .env.local> run --no-override -- python
scripts/probe_b01_snapshot_restore.py --registration <current-domain-registration>
--output /tmp/gauntlet-c01e-live-restore-current-domain-20261016 --execute
--authorize-spend`. It returned `status=passed`,
`synthetic_build_receipt_verified=true`, `gate_status=not_tested`, no cleanup
errors and no pending sandbox IDs. It independently verified each restored Git
SHA, fixture-state digest, fixed startup, `/checkout` readiness and exact
`/api/build-info` response. Sandbox IDs in the sanitized report are
`f5d21668-9ff4-4f81-b3e9-5871cc4bb580` (base) and
`9fbfabda-784e-4659-9c25-9412ac1681ae` (head); both were deleted. The
report explicitly says `sandbox_image_attested=false`. No Anchor browser or
Bedrock model ran, so P1 Gate remains open.

On the integrated tree, the rebuilt fixture passed `npm run build` on both
revisions. Headless Chrome with one frozen, diff-cited scripted plan produced
two `pass` observations on base and two `fail` observations on head. Reports:
`/tmp/gauntlet-c01d-base-probe/report.json` and
`/tmp/gauntlet-c01d-head-probe/report.json`; shared plan hash
`b4e27820046f163f71b45924708aa9359db519d7c53f4d9d4efebec469d7bca0`.
Both probes verified the checkout SHA and local compiled build receipt. The
running server source is still operator asserted, and the plan was scripted;
this is a local diagnostic, not a confirmed P1 regression or provider smoke.

## Current checkpoint (2026-10-15)

P0's joint offline gate is integrated on main: dashboard #3 (`d5255f3`)
and the P0-only checkpoint #29 (`4c12476`). The API consumes A's frozen
goldens, B's fake worker and trusted oracle, and C's route/dashboard displays
the resulting recorded fail/fail/pass outcomes. The response and page explicitly
say `offline_recording`; this is not live browser or provider evidence. The
goldens are packaged as resources so both fake and offline routes also work
from an installed wheel. The three packaged copies are checked byte-for-byte
against A's canonical files in the test suite.

P1 preparation is now in main: C's optional live-provider pins #21 (`3b0592b`)
and registered Cartwheel fixture #4 (`5a8d93f`). The manifest carries distinct
base/head SHAs and checksum; its API route also works from an installed wheel.
On main at `5a8d93f`, `.venv/bin/python -m pytest -q` passed 149 tests,
`.venv/bin/ruff check .` passed, `.venv/bin/mypy services/gauntlet/src` checked
39 files, dashboard lint/typecheck/4 tests/build passed, and
`uv build --package gauntlet-control --out-dir /tmp/gauntlet-main-c01-dist` produced a
wheel and sdist. A booted local API returned HTTP 200 for the Cartwheel change
request, and headless Chrome rendered its actual base/head SHAs with the honest
`not_tested` finding status.

`.venv/bin/python scripts/probe_sdk_inventory.py --ui-preflight` on main exits
2: Daytona 0.224.1, Anchor 1.0.1 and Playwright 1.64.0 are installed, while
`RUN_LIVE_INTEGRATIONS=1`, both provider keys and
`GAUNTLET_ALLOWED_TARGET_IDS=cartwheel-fixture` are absent from the process.
No provider call or spend occurred. B-01a remains `not_tested` until explicit
spend authorization, those local inputs, a permitted Daytona runtime/preview,
and the one-environment screenshot/cleanup smoke are recorded here. The
2026-10-14 readiness and branch notes below are historical snapshots.

### B-01d local evidence storage (2026-10-15)

The B-owned `LocalArtifactStore` implements the frozen `ArtifactStore` port for
sanitized collector bytes. It assigns IDs, hashes content, writes a complete
binding and bytes as one file before publishing the ID, and reads them back
after a new store instance opens the same directory. Local tests exercise
cross-attempt rejection, malformed IDs, invalid media/empty bytes and tampered
content through the independent `check_evidence` function. This is a local
filesystem adapter, not an Anchor collector or a live provider smoke. The
B-01d checkbox stays open until browser geometry, click receipts and screenshots
are captured and bound to real base/head environments.

### B-01d2 stored browser oracle bridge (2026-10-15)

`StoredBrowserOracle` reads every artifact named by a completed browser
observation, checks the stored bytes and binding against the trusted run,
attempt, environment, revision, fixture and step, and validates the fixed
measurement format before constructing `ClickEvidence` for the existing hard
oracle. Missing or corrupted JSON/PNG, absent trusted click receipt, and an
identity mismatch return `inconclusive`. The verifier also hashes the exact
bytes it parses, so inconsistent consecutive store reads cannot create a pass.

The local Chrome diagnostic now runs this bridge after the typed browser
steps. At 375×812, Cartwheel base returned `pass` and head returned `fail`:
`/tmp/gauntlet-b01d2-{base,head}/report.json` and `final.png`. These are
local generated checkouts with a fixed diagnostic plan. The running server's
source revision is still operator asserted, and no Daytona/Anchor session or
independent diff-driven plan was used. These verdicts do not close P1 live
acceptance or establish a confirmed Gate regression.

### B-01 P1 local frozen-plan diagnostic (2026-10-15)

The B-owned `probe_p1_local_gate.py` composes A's real `GitRepositoryInspector`,
`AttackPlanner`, validator and `PlanChangeUseCase` with B's typed `UIWorker`,
local Playwright browser, stored evidence verifier and hard click oracle. A
scripted model response proposes the same narrow Checkout probe for a cited UI
surface; the validator accepts or rejects it, and `plan_frozen` is persisted
before browser execution. This measures the integration path, not model
hypothesis quality. No Bedrock, Daytona or Anchor call occurs.

The generated Cartwheel base (`2265fb61`) and Help-button head (`ab4f8204`)
used the same frozen plan hash
`ad172235a3be83ae1238b944fbf4cdaca7ed52f4a77a9f37e24471e020661cc2`.
Two independent Chrome attempts passed on base; two failed on head. A separate
synthetic clean commit (`7af5232f`) changed only product-page copy; its own
diff-cited UI plan produced two passes. Reports with observation and artifact
IDs are `/tmp/gauntlet-b01e-{base,head,clean}/report.json`; a checked
cross-report summary is `/tmp/gauntlet-b01e-summary.json`. The clean control
checkout is `/tmp/gauntlet-clean-fixture`.

Each checkout SHA was verified before its local Next.js build and browser run.
The server's running source remains operator asserted; the planner response is
scripted, not an independent model hypothesis, and cloud isolation was not
tested. The full P1 acceptance gate and confirmed regression status remain open.

### B-01f paired environment lifecycle (2026-10-15)

The B-owned `gate_environment_pair` context manager provisions base and head
through the existing `SandboxProvider` port. It rejects a mismatched target,
revision, fixture ID or checksum, verifies both fixture states after both
environments exist, and releases both handles on normal exit, partial failure
or cancellation. This prevents an unverified base/head pair from reaching UI
execution. Offline tests use the fake sandbox only; no Daytona resource was
created. Server revision attestation, snapshot registration, signed previews,
Anchor sessions and genuine provider cleanup still require live validation.

### B-01g provider-smoke runner preparation (2026-10-15)

`scripts/probe_b01_provider_smoke.py` now has a credential-free preflight and
an explicit `--execute --authorize-spend` path. The latter composes the pinned
Daytona/Anchor adapters with B's paired environment manager and a fixed
`/checkout` navigate-and-capture probe. It verifies each stored PNG hash,
media type and exact evidence subject, then reports sanitized environment and
artifact IDs plus pending cleanup IDs. It never logs API keys, proxy password or
signed preview origins. `gate_status` remains `not_tested` even if this narrow
provider connectivity smoke passes; no click oracle, server-source attestation
or proxy-policy proof is included. No provider call has yet been run.

The operator registration is a JSON file outside Git containing exactly the
fields of `RegisteredTarget`: `target_id`, `fixture_id`, `fixture_checksum`,
`fixture_state_digest`, `fixture_state_path`, `repo_path`, `preview_port`,
`preview_domain_suffix`, `ready_path` and `snapshots` (two entries with
`source_sha`, `snapshot`, `image_digest`). The two SHAs, target, fixture ID and
checksum must equal `apps/cartwheel/fixture-manifest.v1.json`; both snapshots
must declare the same pinned image digest. The signed preview must serve the
registered readiness path. This file must contain no credentials.

Before a paid run, provision those base/head Daytona snapshots and the exact
fixture-state file in each; configure a reachable Anchor custom proxy that
enforces the signed preview origin; set `RUN_LIVE_INTEGRATIONS=1`,
`GAUNTLET_ALLOWED_TARGET_IDS=cartwheel-fixture`, `DAYTONA_API_KEY`, the HTTPS
`DAYTONA_API_URL`, `DAYTONA_TARGET`, `ANCHOR_API_KEY`, `ANCHOR_PROXY_SERVER`,
`ANCHOR_PROXY_USERNAME` and `ANCHOR_PROXY_PASSWORD` in the process environment.
`DAYTONA_TARGET` and the three `ANCHOR_PROXY_*` variables are not in
`.env.example` and must stay local. The command is
`uv run --frozen --no-sync --group live-providers python scripts/probe_b01_provider_smoke.py --registration <local-json> --output <local-dir> --execute --authorize-spend`.
Without `--execute`, the command only prints missing prerequisite names and
pinned SDK versions. The `--authorize-spend` flag is an operator opt-in, not a
cost limiter. A full P1 Gate run also needs server revision attestation,
verified egress policy, a genuinely model-selected frozen plan, click evidence,
and base/head attribution.

The local preflight with `--execute` and no registration or credentials exited
2 with `not_tested` and only missing prerequisite names; it created no provider
resource. The new port composition passed 8 focused offline tests, and an
independent headless Chrome loopback probe produced two distinct PNG artifacts
for base/head through the same capture function. The Chrome probe used fake
sandboxes and a local static page, so it does not establish Daytona/Anchor
connectivity or Cartwheel behavior.

### B-01c1 browser evidence identity (2026-10-15)

The worker now requires a trusted, preallocated `EvidenceSubject` before it
opens a browser and uses that subject's observation ID in its result. The
browser port receives the subject at session open; the worker and fake reject
environment/source/fixture mismatches, a non-browser collector, or a step index
at session scope. The offline gate allocates distinct attempt and observation
IDs for each recorded run. This establishes the input boundary for a live
collector; no Anchor screenshot, action receipt, or Daytona environment has
been captured by this ticket.

### B-01c2 local browser evidence capture (2026-10-15)

`BrowserEvidenceCollector` uses fixed inspection and click instrumentation on
an authorized synthetic page. It records the CTA rectangle and center hit
target, dispatches a real browser mouse click, records its trusted recipient,
and stores JSON plus screenshots through `LocalArtifactStore`. Inspection is
bound to step 2, click JSON/PNG to step 3, and a final-state PNG to step 4.
The local probe reopens each artifact and calls `check_evidence` with the
expected run/attempt/observation/environment/source/fixture/step subject.

With Playwright 1.64.0 and Google Chrome 155.0.8059.41, the local 375×812
headless probe against the generated Cartwheel commits recorded:

- Base `2265fb61e3fcd71c2def54f739adcf5adf2ade99`: inspect `ok`, click
  `ok`, one order POST, one server-retrievable receipt and four verified
  artifacts. Report and final screenshot:
  `/tmp/gauntlet-b01c2-base-final-v2/{report.json,final.png}`.
- Head `ab4f82048a9e673dd0bf1150bbebbbb4cdbc1f68`: inspect `ok`, click
  `blocked` by Help, zero order POSTs, zero receipts and four verified
  artifacts. Report and final screenshot:
  `/tmp/gauntlet-b01c2-head-final-v2/{report.json,final.png}`.

The probe checks the fixture checkout SHA, confines page requests to one
loopback origin and blocks service workers. It does not verify the revision of
the running server. Its click listener runs in the target page's JavaScript
world, so this remains a local diagnostic, not independent hard-oracle proof.
No Daytona or Anchor resource was used. Re-run the probe with
`uv sync --frozen --group live-providers`, a built synthetic fixture on port
3100, and `uv run python scripts/probe_browser_evidence.py {base|head}
--origin http://127.0.0.1:3100 --chrome <local-chrome-path>
--fixture-repo <generated-fixture-checkout> --output <local-output-dir>`.

### B-01c3 local browser port (2026-10-15)

`LocalBrowserProvider` implements the frozen `BrowserProvider` port around an
injected Playwright browser and the B-01c2 collector. It accepts only an exact
loopback HTTP preview origin, opens an isolated context with service workers
and downloads disabled, aborts cross-origin requests and all redirects,
closes popups, and
translates the typed UI steps. A prohibited key chord or out-of-order step is
blocked; context cleanup is idempotent. The adapter makes no Daytona or Anchor
call. Context routing is not a DNS/network egress boundary for a cloud run.
Playwright only routes the first request in a redirect chain, so this adapter
fetches with `max_redirects=0`, denies 3xx responses, and fulfills only the
non-redirect response. The Chrome scope probe recorded blocked redirect,
subresource and popup attempts with zero requests reaching a second loopback
server: `uv run --frozen --group live-providers python
scripts/probe_local_browser_scope.py --chrome <local-chrome-path>`.

With Playwright 1.64.0 and Google Chrome 155.0.8059.41, the local port probe
ran navigate, resize, inspect, click and capture on the generated Cartwheel
base/head commits at 375×812. Base outcomes were five `ok` records; head
outcomes were `ok`, `ok`, `ok`, `blocked`, `ok`. Both runs verified four stored
artifacts against their exact step subjects. The base final screenshot shows
an order receipt; the head final screenshot shows Help over the CTA. Reports
and screenshots are `/tmp/gauntlet-b01c3-{base,head}-final/{report.json,final.png}`.
The checkout SHA is verified, while the running server source is operator
asserted. No hard-oracle or provider acceptance checkbox is closed. Repeat
with `uv sync --frozen --group live-providers`, the built synthetic fixture on
port 3100, and `uv run --frozen --group live-providers python
scripts/probe_local_browser_provider.py {base|head} --origin
http://127.0.0.1:3100 --chrome <local-chrome-path> --fixture-repo
<generated-fixture-checkout> --output <local-output-dir>`.

### B-01c4 Anchor offline browser adapter (2026-10-15)

`AnchorBrowserProvider` implements the browser port using the same typed-step
and exact-origin Playwright guard as `LocalBrowserProvider`. It validates the
evidence subject and signed HTTPS preview origin before opening a paid cloud
session. It closes the isolated context, CDP connection, then Anchor session;
failed cleanup stays retriable. The SDK wrapper requires
`RUN_LIVE_INTEGRATIONS=1`, an explicit API key, and a configured custom egress
proxy before session creation. Anchor 1.0.1 installed signatures were checked
for `sessions.create_session`, `browser.connect`, and
`sessions.delete_session`. No provider call was made.

The Anchor SDK exposes custom proxy configuration but no verified per-session
domain allowlist. Playwright routing is an additional guard, not a network
isolation proof. B-01c live acceptance remains open until an operator-supplied
egress proxy enforces the exact Daytona preview origin and a live smoke test
covers redirect, popup, subresource and non-HTTP egress from the cloud session. An
approved Daytona preview, Anchor credentials, proxy policy, and authorized
provider spend are required for that smoke.

### B-01b registered Daytona sandbox adapter (2026-10-15)

The B-owned `DaytonaSandboxProvider` now consumes operator-registered snapshot
IDs for specific target/source SHA pairs. Registration requires one declared
image digest across base/head, the same fixture template checksum, an expected
SHA-256 of actual fixture-state bytes, fixed checkout and fixture-state paths,
a preview domain suffix and a readiness path. Unknown target, SHA, fixture or
unsupported replay mode is rejected before a create call. After create, the
adapter reads `git rev-parse HEAD` in the registered checkout directory,
downloads and hashes the fixture-state file, validates the signed preview
origin, and polls a 200 readiness response. Any mismatch or timeout deletes
the partial sandbox; failed deletion leaves its resource ID in
`pending_cleanup_ids` for a scoped retry. `verify_fixture` reads source and
state again. The SDK wrapper uses `CreateSandboxFromSnapshotParams` with
`public=False` and `network_block_all=True`, requires
`RUN_LIVE_INTEGRATIONS=1` before create, and deletion waits for completion.
No planner-provided build or shell command is run.

Daytona 0.224.1 installed signature inspection matched the calls used here:
`AsyncDaytona.create(params, timeout=...)`,
`AsyncDaytona.delete(sandbox, timeout=..., wait=True)`,
`AsyncSandbox.process.exec(command, cwd=..., timeout=...)`,
`AsyncSandbox.fs.download_file(path)` and
`AsyncSandbox.create_signed_preview_url(port, expires_in_seconds=...,
request_timeout=...)`. Nine offline tests pass with a fake runtime and a real
loopback HTTP readiness probe;
this is not a provider smoke. The B-01b and B-01a live checkboxes stay open.

At this earlier B-01b checkpoint, the generated repository had no Daytona
snapshots or `fixture-state.json`, and no server revision attestation or ready
endpoint was provisioned in Daytona. Before a live run, build and register two
private snapshots from the pinned base/head commits with the same actual image
digest, include the same deterministic fixture-state file in each, provide a
running synthetic app and health path, and register the preview proxy domain.
Then supply `DAYTONA_API_KEY`, Daytona HTTPS API URL/region, the approved target
allowlist, `RUN_LIVE_INTEGRATIONS=1` and explicit provider spend authorization.
The signed preview URL contains a bearer token in its hostname; never log the
full `EnvironmentHandle.preview_origin`. VM fork is not used or claimed.

### Cartwheel local checkout workflow (2026-10-15)

C's fixture now has a synthetic, in-process order endpoint. A successful
Checkout click produces a server receipt retrievable by ID; invalid item input
returns 400 and an unknown receipt returns 404. The deterministic rebuilt
base/head SHAs are `2265fb61e3fcd71c2def54f739adcf5adf2ade99` and
`ab4f82048a9e673dd0bf1150bbebbbb4cdbc1f68`; the template checksum is
`99871717d61ee4d0b1bfd105b983bee4330ea425d92c537d2acb7022b6529b59`.
Chrome 155 local headless runs at 375, 768 and 1280 px, twice per width, show
base Checkout receipts at all widths; head Help receives the mobile/tablet
clicks without an order, while desktop Checkout creates retrievable receipts.
The probe records DOM hit target, trusted click recipient, screenshots and
receipt IDs. Source SHA is operator asserted, orders are process-local, and
no Daytona or Anchor resource was used. These results are local diagnostics,
not P1 hard-oracle confirmation.

## 2026-10-14 / B-00 / offline implementation and documentation review

The B branch consumes A-00 through `8396d8e` (including oracle descriptors).
No provider SDK is installed, pinned, or smoke-tested by this ticket. These are
published versions observed from public PyPI metadata, not approved dependencies:

| Distribution | Published version observed | Installed / live smoke |
|---|---|---|
| daytona | 0.224.1 | absent / NOT RUN |
| anchorbrowser | 1.0.1 | absent / NOT RUN |
| arize-otel | 0.14.1 | absent / NOT RUN |
| arize | 8.59.1 | absent / NOT RUN |
| surrealdb | 2.0.0 | absent / NOT RUN |
| surrealdb-memory | 1.0.0b1 | absent / NOT RUN |
| boto3 | 1.43.113 | absent / NOT RUN |
| playwright | 1.64.0 | absent / NOT RUN |

Reproduce with `.venv/bin/python scripts/probe_sdk_inventory.py --published`.
Omit `--published` for a local inventory without network access. The first urllib
metadata attempt failed with a local CA trust error; the committed probe uses
the existing httpx development dependency with certificate verification enabled.

Documentation checked, without creating resources:

- [Daytona Python](https://www.daytona.io/docs/en/python-sdk/): sync and async create/process APIs are documented. VM fork entitlement, signed preview policy, fixture reset, and cleanup still require live verification.
- [Anchor Python SDK](https://github.com/anchorbrowser/AnchorBrowser-SDK-Python): current examples use `sessions.create_session` and `browser.create()`/`browser.connect()`. SDK default key name is `ANCHORBROWSER_API_KEY`; the repository uses `ANCHOR_API_KEY`, which a future adapter must explicitly pass as `api_key`. Never assume the SDK reads the repository variable automatically.
- [Arize OTEL source documentation](https://github.com/Arize-ai/arize-otel-python): `arize.otel.register` accepts space, key, and project configuration. A successful export and evaluated experiment remain unverified; [evaluation documentation](https://arize.com/docs/ax/get-started/get-started-evaluations) is separate from tracing.
- [SurrealDB Python](https://surrealdb.com/docs/languages/python): `AsyncSurreal`, connection/authentication, namespace/database selection, and parameterized queries are documented. No database was started or queried here.
- [Agent Memory Python](https://surrealdb.com/docs/agent-memory/integrations/sdks/python): the independently versioned `surrealdb-memory` distribution is exposed through the prerelease `surrealdb[memory]` extra and `surrealdb.memory`. Endpoint, context, and API key are explicit constructor inputs. Stable core 2.0.0 is not evidence that the memory extra resolves; C must resolve and approve a compatible prerelease lock.
- [Bedrock Converse](https://docs.aws.amazon.com/boto3/latest/reference/services/bedrock-runtime/client/converse.html): model ID, messages, inference/tool configuration are documented. Account/region/model access and genuine structured output remain unverified.

### Offline B-00 composition

`AttackSpec` golden → registered fake environment → recorded browser steps through
`UIWorker` → `Observation` → fixed trusted oracle → A's pure `classify_gate` →
`FakeRunStore` event. `test_b00_integration.py` runs this path with socket connections
forbidden and explicitly labels the result `offline_recording`.

- The store requires an explicit `initial_sequence`; use `1` for the current event golden. A/C must choose the production initial sequence before API integration. Stored payloads and returned events are copied so consumers cannot rewrite history.
- The browser replays exact typed steps for the registered source/fixture/checksum, uses reserved `.invalid` origins, and blocks recorded off-origin redirects. It does not run a real browser.
- The fixed UI oracle consumes trusted internal `ClickEvidence`, bound to observation, attack, environment, source, checksum, step, and registered primary target. Text in `detail` cannot establish failure. No runtime predicate registration exists. P1 must add a trusted collector/artifact binding; this is not a new public DTO.
- Replay only returns an exact preloaded result. Missing historical pins, critical missing inputs, or an absent recording yield `not_replayable`. No tool execution callback exists.
- `UIWorker` bounds actions/runtime and attempts session closure on success, failure, timeout, and cancellation. Cleanup has a separate timeout of at most five seconds (or the smaller execution budget); failed cleanup yields `environment_error`. Retried orphan cleanup remains a later integration requirement. It never assigns a Gate verdict.

### Real local headless diagnostic (not the P1 acceptance gate)

Source fixture templates: C branch commit `748b7be`.
Built by C's `scripts/build_cartwheel_fixture.py` in a temporary detached worktree:

- Base `584c6282d6274a3d5558d90884786f102972593c`.
- Head `5d00edbe264336f97bad8b0073e581e99fca662d`.
- Template checksum `9e16231c3617011fbc159da71d4b4acaa864d961e9fd1c9990ef6cf81243b5dc`.
- Node v23.11.0, Next 15.5.28, Chrome 155.0.8059.41; both base and head `npm run build` passed with the same local dependency installation.

Start the generated fixture on loopback with
`node node_modules/next/dist/bin/next start --hostname 127.0.0.1 --port 3100`, then:

```bash
node scripts/probe_headless_ui.mjs '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' artifacts/b00-browser/head 5d00edbe264336f97bad8b0073e581e99fca662d
node scripts/probe_headless_ui.mjs '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' artifacts/b00-browser/base 584c6282d6274a3d5558d90884786f102972593c
```

Rebuild/restart the correct fixture revision before each command. Each probe
starts a fresh headless Chrome profile, restricts page requests to that loopback
origin, dispatches actual mouse input, and closes Chrome/removes its profile.
Each width (375, 768, 1280; height 812) was repeated twice. All six head center
clicks hit and were received by `help-button`; all six base center clicks hit
and were received by `checkout-primary-action`. JSON reports and twelve PNGs
are in the ignored `artifacts/b00-browser/{base,head}/` directories.

The CLI revision is operator asserted: the probe does not verify the running
server's build SHA. The captured initial reports used the field `sourceSha`;
the current script names it `operatorAssertedSourceSha` to make that limitation
explicit. The separate checkout/build/start command record establishes which
fixture was served during this diagnostic; the probe alone cannot establish it.

This is a directed local diagnostic, not blind planner discovery or Daytona /
Anchor proof. The fixture has no order-submission handler, so results establish
DOM click delivery only. Keyboard fallback, fixture runtime state checksums,
legitimate order completion, and an unrelated clean PR remain P1 gates. The
temporary fixture install reported two dependency advisories; C owns dependency
review and lock changes.

### Handoff and remaining gates

2026-10-14 follow-up: A's review of PR #7 confirmed structural port compatibility
and reported a clean merge/test run against the A stack, but did not approve the
PR. GitHub's scaffold CI failed 25 B tests because it installs pytest without
pytest-asyncio. B tests now use explicit `asyncio.run` scenarios, preserving all
18 async test bodies and assertions. `.venv/bin/python -m pytest -q -p no:asyncio`
passes all 113 tests; no CI/dependency ownership change is needed. All eight PRs
were still open at this follow-up, so no phase gate has advanced on main.

- C composes the B adapters into the real API; this branch does not change C's API/dashboard or generated contracts.
- A plus another appropriate owner must review the oracle/evidence boundary; shared changes require the repository's A/B/C review.
- Full main-tree integration tests/build happen after reviewed merges. A/B/C branches remain open; branch-local success does not complete that gate.
- Repository-wide Ruff currently reports the existing C-owned `test_api.py` import ordering. Format check reports the two existing master-plan Markdown code blocks. B-owned Python lint/format and whole-source mypy are checked separately; these baseline failures are not silently fixed across ownership boundaries.
- Independent review reproduced two edge cases, now covered by regression tests: missing/inconsistent click receipt must be inconclusive, and a hung browser close must time out. The main-tree baseline (before these branches are integrated) passed 11 tests and built a wheel; this does not verify the B changes on main.
- Live provider setup requires C-approved pinned SDK dependencies, explicit `RUN_LIVE_INTEGRATIONS=1` opt-in and permitted spend, an authorized target/fixture, Daytona key/endpoint and runtime quota, Anchor key and reachable allowlisted preview, Arize key/space/project, Surreal core URL/namespace/database/auth, separate Memory endpoint/context/key/scopes, and AWS credential chain/region/model access. These prerequisites are phase-specific; B-00 requires no provider credentials.

### Incoming PR compatibility follow-up (2026-10-14)

PRs #9 (A-04 lineage), #10 (C offline joint checkpoint), and #11 (C-02
refund fixture) arrived during validation; all eleven PRs remain open. #10
supplies the proposed API/dashboard composition; its Python CI contains the
older B tests and fails for the same missing async plugin fixed by `9c20af6`.
B's two GitHub Python checks passed for that commit. C also reported six test
mypy errors: B now uses `ReplayStatus.MATCHED` and `OracleOutcome.FAIL` at typed
call sites. B test imports follow the incoming C root `src` configuration;
on the older B root use Ruff's explicit `--config 'src = ["services/gauntlet/src"]'`.

A temporary detached checkout merged B with A through #8 and C through #10
without conflicts. Before #10 it passed 203 tests, source mypy (58 files),
Python sdist/wheel, dashboard tests (3), and dashboard production build. With
#10, `.venv/bin/python -m pytest -q -p no:asyncio` passed 204 tests. These are
compatibility checks, not main-tree acceptance or live-provider evidence.
The later-phase #9/#11 were inspected but excluded from this P0 check. #11
explicitly reports an OpenAPI generation conflict with its sibling #10;
C must regenerate from the combined routes during integration.

Incoming C root lint settings also expose nine A-owned test import blocks.
B fixes its four blocks only; full combined Ruff remains an integration gate.
No owner branches or main were merged by this check.

Final combined check with B `b4085a7`, A through #8 and C through #10:

- `.venv/bin/python -m pytest -q -p no:asyncio`: 204 passed, one Starlette deprecation warning.
- `.venv/bin/mypy services/gauntlet/src services/gauntlet/tests/test_b00_integration.py services/gauntlet/tests/test_b00_store_replay.py`: 61 files clean.
- `.venv/bin/ruff check services/gauntlet/tests/test_b00_*.py`: passed.
- `uv build --package gauntlet-control --out-dir /private/tmp/gauntlet-stack-dist`: sdist and wheel passed.
- `corepack pnpm --filter @gauntlet/dashboard test`: 4 passed.
- `corepack pnpm --filter @gauntlet/dashboard build`: passed, including lint/type checking.
- Real process smoke: `.venv/bin/python -m uvicorn gauntlet.api.main:app --host 127.0.0.1 --port 18080`, then `curl --fail --silent http://127.0.0.1:18080/runs/offline-gate`: HTTP success, fail/fail/pass, confirmed_regression/introduced, two ordered events.
- Dashboard started with `NEXT_PUBLIC_GAUNTLET_API_URL=http://127.0.0.1:18080 corepack pnpm --filter @gauntlet/dashboard exec next start --hostname 127.0.0.1 --port 18081`. Existing Chrome ran `--headless=new --disable-gpu --no-first-run --dump-dom --timeout=15000` with a disposable profile against `/gate/offline`. Exit 0; DOM and visually inspected screenshot showed the offline label, verdict, three outcomes, and both events. Local evidence: `artifacts/b00-browser/checkpoint/{page.html,offline-gate.png}`. This tests real rendering of an offline recording, not live worker/browser execution.
- Both GitHub Python jobs for B `b4085a7` passed. #10 needs the updated B commits; its remote CI is still on the older tests.

### B-00 malformed URL regression fix (2026-10-14)

Offline browser review reproduced four failures: malformed IPv6 brackets and
NFKC-invalid host delimiters in preview origins or captured redirects escaped
as bare `ValueError` from `urlsplit`. The adapter now converts malformed origins
to `EnvironmentUnavailableError` and malformed redirects to a blocked action
without recording evidence. The worker reports environment_error or aborted,
respectively; neither yields a conclusive oracle result. Valid same-origin
redirects still return the captured action log. No public interface, origin
allowlist, oracle rule, or live provider permission changed.

Verification in B's worktree:

- `.venv/bin/python -m pytest -q -p no:asyncio services/gauntlet/tests/test_b00_ui.py -k malformed --tb=short`: four failures before the implementation, four passes after.
- `.venv/bin/python -m pytest -q -p no:asyncio`: 118 passed, one existing Starlette deprecation warning.
- `.venv/bin/mypy services/gauntlet/src services/gauntlet/tests/test_b00_ui.py`: 35 files clean.
- `.venv/bin/ruff check --config 'src = ["services/gauntlet/src"]' services/gauntlet/src/gauntlet/integrations/fake/browser.py services/gauntlet/tests/test_b00_ui.py`: passed.
- `.venv/bin/ruff format --check services/gauntlet/src/gauntlet/integrations/fake/browser.py services/gauntlet/tests/test_b00_ui.py`: both files already formatted.
- `uv build --package gauntlet-control --out-dir /private/tmp/gauntlet-b-url-fix-dist`: wheel and sdist passed.

This change exercises only the offline adapter; no additional live-browser or
provider claim is made. Main-tree acceptance remains pending reviewed integration.

## B-01 readiness and execution sequence (2026-10-14)

**Owner:** B. **Phase:** P1 preparation only; P0 main acceptance remains open.
**Goal:** execute the existing typed UI plan against isolated Daytona base/head
previews using Anchor, retain independently verifiable click evidence, and
compare head repetitions against base without revealing hidden truth.
**Spec:** DEVELOPMENT_PLAN.md sections 5, 16 and 18; PHASES.md P1; SECURITY.md.
**Architecture:** preserve SandboxProvider, BrowserProvider, UIWorker and the
independent oracle. Provider SDK objects stay inside integrations. Artifact
storage and evidence collection require the shared contract freeze below.

### Current dependency evidence

- C checkpoint #10 at `3cdeddd` now has green Python/dashboard CI after C changed
  setup to `uv sync --frozen`. Earlier statements that #10 CI is red are obsolete.
- `git merge-base --is-ancestor 1f33292 origin/feat/c-00-gate-checkpoint`
  returned 1: the checkpoint still lacks the latest B fixes.
- All 18 PRs remain open; this is not main-tree acceptance.
- `.venv/bin/python scripts/probe_sdk_inventory.py` completed successfully:
  Daytona, Anchor and Playwright are absent; all live outcomes remain not_run.
- `EvidenceRef` already supplies artifact_id, sha256, media_type, created_at and
  optional trace_id. `ports/storage.py` supplies only RunStore. No ArtifactStore
  port exists in B's current checkout or A's latest inspected branch
  `origin/feat/a-09-dependency-map`. Do not substitute a private public DTO.

### Contract freeze request for A/C (posted as issue #22)

1. Input: trusted collector bytes plus run/attempt/observation identity, media
   type, source SHA and fixture checksum; planner and target content cannot
   supply trusted artifact provenance.
2. Output: the existing EvidenceRef plus a reviewed lookup/binding mechanism
   allowing the verifier to retrieve and hash-check the immutable bytes.
3. Invariant: evidence cannot be overwritten, rebound to another attempt, or
   promoted to trusted evidence from page text; missing/corrupt bytes yield
   inconclusive verification. Credentials and signed preview tokens are excluded.
4. Example existing reference JSON: `{"schema_version":"1.0","artifact_id":"art-shot-001","sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","media_type":"image/png","created_at":"2026-10-14T19:00:00Z","trace_id":null}`.
5. Consumers: B's Anchor collector, RegisteredOracleRegistry and artifact store;
   C's evidence API/dashboard. A owns the port/schema decision and golden; all
   three owners review it before B implements that boundary.

### Ordered deliverables and acceptance

- [x] **P0 integration:** A's golden, B's fake worker/oracle and C's offline
  API/dashboard checkpoint are merged and verified from main as recorded in
  the current checkpoint above. This is an offline gate only.
- [ ] **B-01a provider smoke:** C approves and pins `daytona`, `anchorbrowser`
  and `playwright` in the local dependency lock. Verify signatures against the
  installed versions and official documentation before writing external calls.
  With explicit spend authorization, use one synthetic registered fixture:
  create one Daytona environment, verify revision/checksum/readiness, open its
  approved preview with Anchor, capture one screenshot, then close the browser
  and destroy the environment in bounded cleanup. Record genuine resource IDs,
  sanitized results, versions, elapsed time and cleanup outcome here. Failure
  stays environment_error; an offline response cannot satisfy this acceptance.
- [ ] **B-01b sandbox adapter:** implement existing `SandboxProvider.create`,
  `verify_fixture` and `destroy` under `integrations/daytona/`; tests under
  `services/gauntlet/tests/test_b01_sandbox.py`. Tests cover unknown target/SHA,
  fixture mismatch, readiness timeout, partial-create failure and idempotent
  destruction. Only registered build commands execute; no planner-provided
  shell. Base/head must use equivalent image and fixture state. VM fork remains
  optional; independent sandbox creation must not be described as a fork.
- [ ] **B-01c browser adapter:** implement existing `BrowserProvider` under
  `integrations/anchor/`; tests under `services/gauntlet/tests/test_b01_browser.py`.
  Translate typed steps only. Test viewport bounds, off-origin redirects,
  popups/subresource egress, malformed URLs, timeout, cancellation, failed close
  and repeated cleanup. Generic planner JavaScript/shell is never accepted.
  Navigation routing alone does not establish DNS or network egress isolation.
- [ ] **B-01d trusted evidence:** after the ArtifactStore/binding contract freezes,
  collect bounding rectangles, elementFromPoint, actual click delivery and
  screenshots with artifact hashes. Bind to the actual environment, revision,
  checksum, observation and step. Test missing/corrupt artifacts, wrong source,
  another attempt's evidence, absent click receipt and contradictory hit/receipt;
  each must stay inconclusive. Do not weaken the existing oracle.
- [ ] **P1 acceptance:** A freezes hypotheses from the actual diff and normal
  manifest before actions; repeat selected head attempts, replay the same plan
  on base, and persist evidence/events. Include an unrelated clean change and
  legitimate workflow checks. C's fixture currently establishes DOM click
  delivery, not completed order submission; C must supply the required real
  workflow behavior before claiming that broader acceptance.

### Required operator/project setup

C-approved pinned dependencies and isolated `.venv`; approved synthetic target
repository, actual base/head revisions and runtime fixture checksum; explicit
`RUN_LIVE_INTEGRATIONS=1` and authorized provider spend; Daytona API key, endpoint,
runtime class/quota and preview/network policy; Anchor key and an approved,
reachable preview. Pass repository `ANCHOR_API_KEY` explicitly to the SDK rather
than relying on its differently named default. Keep provider credentials in the
control plane, outside app sandboxes and artifacts. A's planner/model access and
C's evidence/API composition are additional dependencies for the complete P1
loop. No credential values were read or changed during this readiness check.

### Validation commands after each approved implementation slice

Use the approved worktree environment (`uv sync --frozen` once C's lock is in the
checkout), then `.venv/bin/python -m pytest -q`,
`.venv/bin/mypy services/gauntlet/src`, and
`uv build --package gauntlet-control --out-dir /tmp/gauntlet-b01-dist`.
Run the changed-path Ruff checks and the real provider smoke appropriate to that
slice. Require full main-tree tests/build after reviewed integration. A plan or
an SDK inventory is not evidence that these future commands passed.

### Executable local UI preflight

Run `.venv/bin/python scripts/probe_sdk_inventory.py --ui-preflight` before
attempting B-01 live setup. It reads only installed distribution metadata and
process environment, never provider APIs or dotenv files. It prints booleans
for configuration presence, installed versions, and `status: not_tested`.
Exit 2 means a local prerequisite is missing; exit 0 means only that local
prerequisites are present, not that credentials work or live execution is
approved. `--published` and `--ui-preflight` are mutually exclusive.

Required process environment: `RUN_LIVE_INTEGRATIONS=1`, non-placeholder
`DAYTONA_API_KEY`, non-placeholder `ANCHOR_API_KEY`, and
`GAUNTLET_ALLOWED_TARGET_IDS` containing the exact `cartwheel-fixture` ID.
Use the project's trusted environment-loading mechanism or export the variables
in the launching shell; merely placing them in `.env.local` does not load them
for this script. Never paste keys into a PR, command log or chat. C must pin
Daytona, Anchor and Playwright in the approved local dependency mechanism. The
runtime, quota, preview, fixture and review requirements above still apply.

Actual run in B's worktree returned exit 2: all three SDKs, both keys, live
opt-in and target configuration are absent. No keys were printed or network
requests made. This reports unavailable local setup, not a provider outage.

Verification:

- Seven preflight tests failed before implementation and passed afterward.
- `.venv/bin/python -m pytest -q -p no:asyncio`: 125 passed, one existing Starlette warning.
- `.venv/bin/mypy scripts/probe_sdk_inventory.py services/gauntlet/tests/test_b01_preflight.py`: two files clean.
- `.venv/bin/ruff check scripts/probe_sdk_inventory.py services/gauntlet/tests/test_b01_preflight.py`: passed.
- `uv build --package gauntlet-control --out-dir /private/tmp/gauntlet-preflight-dist`: wheel and sdist passed.

No headless run is needed for this metadata/configuration probe; previous
headless evidence applies only to the recorded fixtures/checkpoint. Integrated
main acceptance and genuine provider smoke remain outstanding.

## Cross-owner review and SDK signature check (2026-10-14)

B reviewed A-00 PR #1 (approved), A-03 PR #6 (approved), and A-04 PR #9
(approved). A-02 PR #8 has a B change request: its route-prefix check accepts
`/checkout/%2e%2e/admin` under `/checkout`, while a browser URL parser resolves
it to `/admin`. A needs to reject or canonicalize encoded dot/path segments
before accepting a model-proposed route. B's eventual live browser adapter must
also verify the final URL after redirects. These reviews do not merge any PR.

B approved C's optional SDK pin PR #21 for dependency installation and signature
checking. In a detached, worktree-local Python 3.12 environment,
`uv sync --frozen --group live-providers` resolved and installed Daytona 0.224.1,
Anchor 1.0.1 and Playwright 1.64.0. The branch's 85 Python tests passed. The
installed methods report:

- `AsyncDaytona(DaytonaConfig(...))`; `AsyncDaytona.create(params, timeout=60)`
  returns `AsyncSandbox`; `AsyncDaytona.delete(sandbox, timeout=60, wait=False)`.
- `DaytonaConfig` accepts explicit `api_key`, `api_url`, `server_url` and `target`.
  `AsyncSandbox.get_preview_link(port, request_timeout=None)` is present.
- `AsyncAnchorbrowser(api_key=..., timeout=..., max_retries=0)` accepts the
  repository's key explicitly. Its `browser.create()` and `browser.connect(id)`
  are asynchronous context managers, not direct browser instances.
- `async_playwright()` is available; no browser binary was downloaded here.

These are inspected signatures, not a successful service call. No keys were read
and no provider resource was created. A/C still need to review the shared
root dependency change and resolve the stacked lockfiles.

A temporary detached checkout combined B `03314ae`, A through A-09b
`2df2193`, and C's P0 checkpoint `7c8bcc6` with no merge conflicts. With
`uv sync --frozen` in that checkout:

- `.venv/bin/python -m pytest -q -p no:asyncio`: 327 passed, one Starlette
  deprecation warning.
- `.venv/bin/mypy services/gauntlet/src`: 78 source files clean.
- `.venv/bin/python scripts/export_schemas.py` followed by
  `git diff --exit-code packages/contracts/jsonschema`: 24 schemas, no drift.
- `uv build --package gauntlet-control --out-dir /private/tmp/gauntlet-abc-stack-dist`:
  wheel and source distribution passed.
- `corepack pnpm --filter @gauntlet/dashboard test`: 4 passed.
- `corepack pnpm --filter @gauntlet/dashboard build`: passed.
- `.venv/bin/ruff check . --output-format concise`: 16 import-order errors in
  A-owned tests under C's root `src` setting. B's tests are clean; A/C must
  resolve the whole-tree lint gate during integration.

The first exploratory schema export in that temporary checkout used B's
editable interpreter without its checkout source on `PYTHONPATH`, producing
three local schema diffs. After restoring only those temporary generated files
and using the checkout-local `.venv`, the 24-schema export was clean. No shared
branch or main file was changed by the compatibility run.

P1 artifact binding request is now tracked at https://github.com/rudraasakariya/gauntlet/issues/22; no shared port/schema was changed on B's branch.

## Parallel P1 implementation and local evidence (2026-10-15)

A-01c adds an opt-in Bedrock planning probe using boto3/botocore 1.43.114.
Installed Converse signatures and a botocore Stubber request were checked against
AWS's Converse and Config documentation; this was an offline SDK shape check,
not an AWS response. The adapter limits input/output size and SDK connect/read
waits (5/60 seconds, one attempt); those are not a total wall-clock deadline.
The neutral prompt supplies no known fixture defect or viewport answer. Accepted
plans pass existing validation and freeze before any execution; this probe does
not execute them or claim a Gate verdict.

C-01c embeds a clean generated fixture commit in `/api/build-info`. Registered
base is `e5ab64c85d3080b2982c68da23ab677ce8cb5a69`; head is
`d3ebde5c6d71cfde1acae7be768438a241afd19b`. Existing fixture snapshots must be
rebuilt for these revisions. B-01k checks the receipt before local planning or
browser work, rejects redirects/compressed/oversized/malformed responses and
mismatched revisions. This trusted synthetic build receipt does not attest to
hostile source or a container image.

Real production Next builds and local headless Chrome runs on the integrated
branch produced two failing head observations and two passing base observations.
Both used frozen plan hash
`659662f940dd7235d3f4a9e7de723aaadab99253e642edf8841183afd854fd4f`.
Reports: `/tmp/gauntlet-parallel-head/report.json` and
`/tmp/gauntlet-parallel-base/report.json` (ephemeral local evidence).
Checking out base while the compiled head server still ran was rejected before
browser execution. These are scripted local probes, not blind model acceptance.

B-01h/B-01i/B-01j add cancellation and cleanup regressions for the UI worker,
Daytona sandbox adapter and Anchor browser adapter. Cleanup retains retryable
resources and bounds caller waits; an SDK task that ignores cancellation can
remain in the background until it cooperates. No genuine cloud resources were
created, so cloud cleanup behavior remains unverified.

### Complete prerequisites for the next genuine planning run

- Install project-local dependencies: `uv sync --frozen --group live-providers`.
- Configure the AWS credential chain (profile or role), Bedrock model access and
  invocation permission, explicit approved model ID and AWS region.
- Supply an authorized repository and matching ChangeRequest JSON, and a new
  writable output destination.
- Run `scripts/probe_p1_model_plan.py` with `--repository`, `--change-request`,
  `--model-id`, `--region`, `--output`, `--execute`, `--authorize-spend` and
  `RUN_LIVE_INTEGRATIONS=1`. Do not place credential values in command arguments
  or commit them. The probe reports plan acceptance separately from Gate status.
- For subsequent hosted execution, the existing provider smoke additionally
  needs Daytona and Anchor credentials, approved snapshots for these exact
  revisions, and approved preview/network configuration. A successful planning
  call alone does not satisfy hosted execution or P1 acceptance.

AWS and Anchor live results remain NOT RUN. Daytona results are recorded in the
2026-10-16 live restore update above. P1 is not yet accepted.

## P1 handoff and infrastructure recheck (2026-10-16)

Main at `37b7758` passed 344 offline tests and the real local headless browser
scope probe (`redirect=blocked subresource=blocked popup=blocked
 off_origin_requests=0`). Provider preflight found the pinned SDKs installed but
no process credentials; this checkout had no `.env`/`.env.local`, and no AWS
shared config/credentials files were present. Credential values were not printed.
The operator reported newly added keys; their location is still needed before
any genuine provider smoke. Absence here is not a claim about other checkouts or
secret managers. All paid/provider live results remain NOT RUN.

PR #43's registry digest pins were independently reviewed and merged. An isolated
Compose test using those exact pinned images and automatically allocated loopback
ports passed SurrealDB health, authenticated `RETURN 1`, and an authenticated
Postgres `cartwheel|1` query. Both reviewer and integrator repeated the smoke.
Synthetic project `gauntlet-pr43-5a691abc` was torn down, including its own volumes
and network, with no remaining project containers. No other project's resources
were changed. Normal startup still needs Docker/Compose, registry access or cached
images, `SURREAL_PASS`, `CARTWHEEL_DB_PASSWORD`, optional `SURREAL_USER`, and free
loopback ports 8001/5432.

A-01d now serializes the existing frozen plan into a strict versioned handoff.
Consumers provide independently trusted change, plan hash, run, model and prompt
identity; the loader checks these and recomputes the existing canonical plan hash.
Malformed/duplicate fields and over-2-MB JSON are rejected. Empty plans remain
`not_tested` and cannot dispatch. This integrity hash is not an authorization
signature. The model CLI retains its report fields and adds `frozen_plan`.

B-01n consumes that handoff with independently supplied expectations and executes
unchanged accepted UI attacks twice against a selected local revision. The
integrated real headless run used one scripted (not Bedrock-generated) receipt:

- Run ID: `local-handoff-smoke`.
- Plan hash: `659662f940dd7235d3f4a9e7de723aaadab99253e642edf8841183afd854fd4f`.
- Base: two `pass` oracle outcomes; head: two `fail` oracle outcomes.
- Both verified compiled build receipts before browser actions.
- Reports/artifacts: `/tmp/gauntlet-p1-handoff-smoke/base/` and
  `/tmp/gauntlet-p1-handoff-smoke/head/` (ephemeral local evidence).
- Invocation wrapper: `.venv/bin/python /tmp/run-gauntlet-frozen-smoke.py base`
  and the same command with `head`; wrapper passes the documented consumer flags
  with trusted expectations saved when the scripted plan was frozen.

This proves saved-plan transport through the real local browser/oracle path. It
does not establish blind model proposal quality, hosted fixture attestation,
restrictive proxy policy, or a final paired Gate classification. Both reports
retain `gate_status=not_tested`. Servers were stopped after the probes.

### Azure OpenAI planner stand-in (2026-10-16)

Decision (A, owner): use Azure OpenAI as a **development stand-in** for the
planner's model port until Bedrock access exists. `integrations/azure_openai.py`
calls the chat-completions REST API with the existing `httpx` dependency, so no
new SDK was added. One attempt, 5 s connect / 60 s read, no redirects or proxy
environment, JSON response format, bounded input/output, and provider error text
never surfaced. Output goes through the same plan validator and freeze as
Bedrock. Probe reports carry `provider: azure` and `sponsor_evidence: false`.

Run: put `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_KEY`
(optional `AZURE_OPENAI_API_VERSION`, `AZURE_OPENAI_REASONING_MODEL=1` for
o-series) in `.env.local`, then
`set -a; source .env.local; set +a; RUN_LIVE_INTEGRATIONS=1 uv run python
scripts/probe_p1_model_plan.py --provider azure --repository <fixture-repo>
--change-request <change.json> --output <new-file> --execute --authorize-spend`.

Offline only so far: request shape and failure handling are checked with an
`httpx` mock transport. **Live Azure result: NOT RUN.** Bedrock remains the
sponsor integration and still needs its own live run.

### Session 1: Gate pipeline composition root (2026-10-16)

`scripts/run_gate.py` runs `RunGateUseCase` (plan freeze -> base/head environment
pair -> UI worker x2 per side -> stored-evidence oracle -> `adjudicate_ui_pair`).
`gauntlet/composition.py` picks adapters; `gauntlet/settings.py` is the only
place that reads environment variables. Every report carries an `adapters`
block, and `mode` is `offline` only when model, sandbox and browser are all
offline.

| Adapter | Flag | Status | Exact live command |
|---|---|---|---|
| Scripted planner | `--model scripted` (default) | offline only, by design | n/a |
| Fake sandbox + simulated layout | `--sandbox fake --browser fake` (default) | offline only, by design | n/a |
| Azure OpenAI planner | `--model azure` | offline-tested, **live NOT RUN** | `RUN_LIVE_INTEGRATIONS=1 uv run python scripts/run_gate.py --model azure` |
| Bedrock planner | `--model bedrock` | offline-tested, **live NOT RUN** (no AWS account) | `RUN_LIVE_INTEGRATIONS=1 uv run --group live-providers python scripts/run_gate.py --model bedrock` |
| Local pre-started servers + local Chromium | `--sandbox local --browser local` | see the local run note below | `CARTWHEEL_BASE_ORIGIN=http://127.0.0.1:3101 CARTWHEEL_HEAD_ORIGIN=http://127.0.0.1:3102 uv run --group live-providers python scripts/run_gate.py --sandbox local --browser local` |
| Daytona + Anchor | `--sandbox daytona --browser anchor` | offline-tested, **live NOT RUN** | `RUN_LIVE_INTEGRATIONS=1 GAUNTLET_DAYTONA_REGISTRATION=<registration.json> GAUNTLET_ANCHOR_REQUIRE_PROXY=0 uv run --group live-providers python scripts/run_gate.py --model azure --sandbox daytona --browser anchor` |

Missing keys stop the run with `{"overall_status": "not_tested", "error":
"missing NAME"}`; the report's `live_readiness_missing` lists unset variable
names only. `GAUNTLET_ANCHOR_REQUIRE_PROXY=0` is weaker isolation (no egress
proxy); it needs an Anchor adapter with a proxy-less constructor
(`SdkAnchorRuntime.without_proxy`), otherwise the run refuses to start.

Offline result (`uv run python scripts/run_gate.py`): `confirmed_regression`,
attribution `introduced`, head 2/2 failures, base 0/2, plan frozen before
`environments_ready`. `--clean`: `passed` (0/2 head, 0/2 base). These are
**simulated-layout** results (box model transcribed from the fixture CSS), not
browser results.

#### Local real-browser Gate run (2026-10-16, Session 1)

Built base `ad74b08` and head `fd32708` with `next build` from clean fixture
checkouts and served them with `next start` on `127.0.0.1:3101` / `:3102`.
Both build receipts named the expected SHA. Then:
`CARTWHEEL_BASE_ORIGIN=http://127.0.0.1:3101 CARTWHEEL_HEAD_ORIGIN=http://127.0.0.1:3102 uv run --group live-providers python scripts/run_gate.py --sandbox local --browser local --run-id local-chromium-1`

Result: `confirmed_regression`, attribution `introduced`, head 2/2 failures,
base 0/2, scripted planner. Click measurements: on head the click at the
Checkout centre was received by `help-button`; on base by
`checkout-primary-action`. This is real headless Chromium (Playwright 1.64,
`/opt/pw-browsers/chromium`) against real Next.js builds on loopback. It is
**not** Daytona or Anchor and not a model-planned run.

### Session 1: Recall pipeline (2026-10-16)

`scripts/run_recall.py` runs `RunRecallUseCase` over `apps/cartwheel/history`
(checksum verified against its manifest): lineage scope -> readiness ->
3 pinned control replays -> 3 counterfactual replays -> materiality verdict,
plus the ledger event audit of `request_refund`. Review output is drafts only.

| Adapter | Flag | Status | Exact live command |
|---|---|---|---|
| Captured-input replay, synthetic agent policy | `--model scripted` (default) | offline only, by design | n/a |
| Captured-input replay, model agent | `--model azure` | offline-tested with a fake gateway, **live NOT RUN** | `RUN_LIVE_INTEGRATIONS=1 uv run python scripts/run_recall.py --model azure` |
| SurrealDB history / lineage | — | **not wired**; file adapter used | plugs in at `composition.build_recall` |

Offline result for trigger `kb-117`: decisions 001, 015 tainted (direct),
009 tainted (second order via `mem-083`), 004 and 012 cleared, 007
not_replayable (tool result not recorded). Event audit: 36 audited, 3
violations (ledger credit to a non-owner), 1 inconclusive, 32 clear. The
offline agent policy is deterministic, so no control mismatch occurs offline;
the control-mismatch path is covered by `test_s1_run_recall.py` with an
unstable model.

### Session 1: P2 AI/tool Gate (2026-10-16)

`uv run python scripts/run_gate.py --change refund-tool` builds the refund
fixture, freezes a plan (the planner was only allowed `ai_agent`/`api` workers
because the diff touches `api/src/tools/`), exports base `0b1b2c4` and head
`b5ea826` per environment with `git archive`, and runs the target's own
`request_refund.ts` in Node 22 (type stripping) through a fixed harness. The
harness, not the agent, writes the ledger snapshot; the `agent.refund_authorized`
hard oracle reads only that snapshot.

Offline/local result: `confirmed_regression`, `introduced`, head 2/2 (ledger
credit for `ord-2001` requested by `synthetic-attacker-01`), base 0/2 (tool
threw `forbidden`). Owner refund passes; a promise without a ledger entry
passes. Adapters: `offline_scripted` planner + `offline_synthetic_agent` +
`local_tool_world` (host subprocess, empty env, 15 s timeout — weaker than a
Daytona sandbox). Live model agent and Daytona-hosted tool world: **NOT RUN /
not built**.

### Session 1: P3 repair loop (2026-10-16)

`scripts/run_repair.py` (two steps): Gate on the refund-tool change -> scripted
fix proposal (restores the owner check) -> prints plan SHA-256 -> a reviewer
approves that exact hash with a dev-grade server-side token
(`GAUNTLET_REVIEWER_TOKENS`, presented via `GAUNTLET_REVIEWER_TOKEN`, never
argv) -> patch applied with `git apply` in a fresh detached worktree, path
allowlist checked before and after -> local commit -> original attack, a
variant (other victim, different wording) and the owner's own refund each run
twice on the patched revision.

Offline/local result: patched commit verified, all checks pass, verdict
`fix_verified_review_required` (review only; nothing merged or pushed). A
stale hash and an unknown token are refused; a reused approval is refused; a
fix that blocks every refund is `fix_rejected` (legitimate workflow broke).
Model fix proposer (`--model azure`): offline-tested shape only, **live NOT RUN**.

### Session 1: P7 memory-informed planning (2026-10-16)

`LearnFromGateUseCase` writes one `TemporalMemoryFact` per confirmed finding
(`verification=confirmed`, `trust=verified_test`, provenance = finding id,
oracle id, head commit). Plans read memory through `MemoryReader` with
`as_of` = plan time, and `select_memory` re-filters (confirmed, trusted,
known and valid at `as_of`, not superseded).

Offline sequence with `--memory local` (file `artifacts/memory/facts.json`):
1. `run_gate.py --memory local --learn` -> `confirmed_regression`, fact
   `fact-finding-attack-ui-primary-action-375-fd32708bcd61` written.
2. `run_gate.py --clean --memory local` -> planner cites the fact and adds a
   768 px attack; both pass (`passed`).
3. `run_gate.py --memory local` -> the memory-added 768 px attack is also a
   `confirmed_regression` (Help covers Checkout below 900 px), which the
   memory-free plan did not test.

`--memory surreal` uses Session 2's `SurrealTemporalMemory`: offline-tested by
Session 2, **live NOT RUN** (`RUN_LIVE_INTEGRATIONS=1 uv run python
scripts/run_gate.py --memory surreal --learn`). The scripted planner's use of
memory is a fixed rule (widen the viewport sweep), not model judgement.

### Session 1: P9 workers (2026-10-16)

| Worker | Oracle (hard) | Adapter | Status |
|---|---|---|---|
| `accessibility` (browser port, `UIWorker(kind="accessibility")`) | `a11y.primary_action_target`: primary action >= 24x24 px (WCAG 2.2 SC 2.5.8) and its centre is not covered | simulated layout / local Chromium / Anchor | offline + **local Chromium run**: `run_gate.py --a11y` -> head 2/2 fail (covered by `help-button`), base 0/2 |
| `api` (`ApiClient` port, `HttpxApiClient`, origin-locked, no redirects) | `api.order_contract`: invalid order bodies refused with 4xx, valid ones 201 with fixed invariants | simulated orders transport (offline), real HTTP for local/Daytona | offline-tested only; live NOT RUN |
| `workflow`, `concurrency` | — | — | **not built** (selector allows them; planner proposals are reported `not_tested` with "no registered executor") |

Local Chromium command: `CARTWHEEL_BASE_ORIGIN=http://127.0.0.1:3101 CARTWHEEL_HEAD_ORIGIN=http://127.0.0.1:3102 uv run --group live-providers python scripts/run_gate.py --sandbox local --browser local --a11y`.

#### P2 model-played support agent (2026-10-16)

`run_gate.py --change refund-tool --agent azure` lets a real model play the target's support
assistant. The model only returns `{"tool_order_id", "reply"}`; the id must match
`ord-NNNN` or no tool call happens; the fixed harness runs the target's tool code and the
ledger oracle decides. Offline-tested with scripted model answers; **live NOT RUN**:
`RUN_LIVE_INTEGRATIONS=1 uv run python scripts/run_gate.py --change refund-tool --agent azure`.

### Post-pull provider readiness and Recall authorization refresh (2026-10-16)

Validated against Daytona 0.224.1, Anchor 1.0.1 and httpx 0.28.1.
Configuration-only readiness with the local environment now reports each sponsor
independently: Daytona ready; Anchor blocked by missing proxy settings; remaining
sponsors missing credentials. Strict execution settings are unchanged.
A genuine read-only `probe_daytona(load_settings(daytona_environment))` returned
`15 snapshots visible`; no resources were created by this check.

Gate now registers Daytona and Anchor client closure on its execution stack.
Normal closure, setup failure and cancellation are covered by three synthetic
lifecycle tests. Anchor probe creation/deletion cancellation and cleanup failures
are covered by focused tests; **live Anchor NOT RUN** (proxy credentials missing).
Replay-triggering Recall reads require reviewer authentication when the composed
runtime uses live providers. The combined API/dashboard passed the 12-step
headless Chrome demo, including public offline Recall and reviewer login.
No full live model/Daytona/Anchor Gate is claimed by these checks.

### Live go-live probes and blind Azure planning (2026-10-16, owner machine)

`scripts/go_live_check.py --probe` with `RUN_LIVE_INTEGRATIONS=1`: **probe ok** for Azure OpenAI
(AI Foundry v1 endpoint, reasoning deployment), Daytona (snapshot list), Anchor (session created
and deleted, WITHOUT egress proxy), Arize (span exported), SurrealDB core (local `surreal`
3.2.3), SurrealDB Agent Memory (hosted context, service principal) and ElevenLabs (key accepted).
GitHub App: not created.

Blind planning, live: `run_gate.py --model azure --sandbox local --browser local` against the
built base/head Cartwheel servers in real headless Chrome. After adding each oracle's evidence
contract to its description and two generic prompt rules (cover every condition a change
creates; oracle/worker pairing), three consecutive runs each planned attacks on both sides of
the changed 900px breakpoint and returned `confirmed_regression` (below: head 2/2, base 0/2) and
`passed` (at/above). One earlier run before the coverage rule planned desktop only and passed,
so planner variance is real. Daytona/Anchor hosted Gate execution: in progress.

### P9 browser workflow evidence (2026-10-16)

`workflow.completion_marker_visible` is registered for the known Cartwheel checkout
only when Gate uses a real local or Anchor browser. The trusted submit selector is
`checkout-primary-action`; the source-reviewed completion marker is
`order-receipt`. A blocked click stops the workflow and the hard oracle reads the
bound click receipt and screenshot before returning `FAIL`. A visible completion
marker after a received click returns `PASS`. Missing or corrupt artifacts remain
`INCONCLUSIVE`. A missing asynchronous receipt currently produces an execution
error/inconclusive result, not a confirmed completion failure.

Headless local Chrome tests executed a successful synthetic checkout flow, an
overlaid/blocked submit, and a delayed order receipt. The combined demo rehearsal
passed offline. These tests do not establish a full live Cartwheel base/head
workflow or an Anchor browser run on this branch.

### Bedrock reasoning-model probe handoff (2026-10-16)

The P1 opt-in planner probe now forwards the validated `BEDROCK_REASONING_MODEL`
setting to `create_bedrock_gateway`, matching Gate composition. A local test using
the real gateway code and synthetic Bedrock response confirmed reasoning blocks
are skipped and no temperature is sent. Invalid settings stop before client
construction. **Live Bedrock probe NOT RUN here:** the local AWS profile is not
available (`ProfileNotFound`).

### Independent provider and browser rerun (2026-10-16)

AWS CLI 2.38.1 was installed in the project-local `.venv` area. A temporary
`hacksprint` profile passed STS identity verification. Bedrock's read-only model
inventory in `us-west-2` listed `us.openai.gpt-6-luna` as an inference profile.
Exactly one paid synthetic Cartwheel planning request used boto3 1.43.114 and
reasoning mode. Bedrock request ID `6a4cab66-dbaf-44c6-bf9a-b89a1137369b`
returned a frozen plan hash
`d874e0453b22fb91c7c44b8aa8cf2e20ece3f308db8d31eafc35e9e99c0f56b3`
with two accepted candidates and zero rejected. **Gate status stayed
`not_tested`.** Both accepted candidates clicked `help-button` while requesting
the `ui.primary_action_reachable` oracle, which requires an action on
`checkout-primary-action`. This is a planner validation gap, not proof of a
working P1 test. No Gate execution followed the model call.

```bash
AWS_PROFILE=hacksprint RUN_LIVE_INTEGRATIONS=1 BEDROCK_REASONING_MODEL=1 \
  .venv/bin/python scripts/probe_p1_model_plan.py --provider bedrock \
  --repository /tmp/gauntlet-a-bedrock-probe.CvMdmU/cartwheel \
  --change-request /tmp/gauntlet-a-bedrock-probe.CvMdmU/change.json \
  --model-id us.openai.gpt-6-luna --region us-west-2 \
  --output /tmp/gauntlet-a-bedrock-probe.CvMdmU/report.json \
  --execute --authorize-spend
```

The request ID came from Bedrock Converse `ResponseMetadata.RequestId` and was
forwarded to the `plan_frozen` event's `trace_id`.

The existing private Cartwheel registration passed `load_registration` against
the committed base/head revisions and fixture checksum. A read-only Daytona SDK
0.224.1 list found both registered snapshots active and zero sandboxes; Anchor
SDK 1.0.1 answered its session-status read. One explicitly authorized hosted
Daytona/Anchor smoke using that registration returned `environment_error` with
`EnvironmentUnavailableError`, zero captures, and Gate `not_tested`. Cleanup
reported no errors and zero pending sandbox/browser/Anchor IDs; a later read
still found zero Daytona sandboxes. No retry was made. Proxyless Anchor remains
weaker egress isolation and does not establish a production-safe Gate run.

```bash
RUN_LIVE_INTEGRATIONS=1 .venv/bin/python -m dotenv \
  -f "$HOME/.config/gauntlet/provider.env" run --no-override -- \
  .venv/bin/python scripts/probe_b01_provider_smoke.py \
  --registration /tmp/cartwheel-b01s-registration-current-domain-20261016.json \
  --output /tmp/gauntlet-b01-anchor-one-shot-20261016-1 \
  --execute --authorize-spend
```

Real local Chrome against built Cartwheel base/head fixtures on ports 3101/3102
confirmed primary-action reachability: base 2/2 passes, head 2/2 failures, with
matching build receipts. A separate full checkout workflow exposed a timing
issue: the local browser adapter clicked after `domcontentloaded` but before
Next.js attached the submit handler. The click receipt said `ok`, yet no
`/api/orders` POST occurred and the completion-marker inspect timed out, so the
workflow was `environment_error`/inconclusive. Waiting for page hydration in a
direct Chrome check produced a base order POST 201 and visible receipt. The
bounded navigation readiness fix in B commit `ae07406` then made the full local
workflow replay conclusive: base navigation/click/receipt completed and the hard
oracle returned `pass`; head navigation completed, the submit click was blocked,
and the hard oracle returned `fail`. These are real local Chrome observations
against synthetic fixture servers, not a hosted Anchor run. The fix still needs
main integration and CI at the time of this entry.

### B/C provider setup and evidence validation (2026-10-16)

GitHub App `gauntlet-nyc-gate` (5347794), installation 172145330, is scoped to
`gauntlet-nyc/gauntlet`: checks write, pull requests/metadata read. App JWT
authentication and one neutral connectivity check succeeded (check 117083989739).
The authorized Smee development relay forwarded a genuinely signed GitHub ping to
`/webhooks/github` with HTTP 202; the initial unsigned ping was rejected with 401.
Pull-request events are subscribed. A real PR opened event reached the relay and
local API, but arbitrary PR revisions remain not tested because execution accepts
registered synthetic fixture revisions only. The API and relay must keep running.

Two bounded Daytona/Anchor pair smokes used the preexisting synthetic registration
and updated proxyless Anchor key. SDK versions: Daytona 0.224.1, Anchor 1.0.1,
Playwright 1.64.0. Both reports remain environment_error / Gate not_tested:
`/tmp/gauntlet-hosted-check-now/report.json` and
`/tmp/gauntlet-hosted-check-fixed/report.json`. Restore, receipt verification, CDP
connection and navigation succeeded. The first capture was JPEG bytes mislabeled
as PNG. The collector now explicitly requests PNG and refuses a mismatched byte
signature before image storage. The repeat still returned non-PNG despite the
explicit request, so hosted screenshot interoperability remains unresolved. No
oracle acceptance was relaxed. Four sandboxes and two Anchor sessions were created
across both attempts; final read-only inventory confirmed zero remaining resources
and no pending cleanup. Billing amounts were not available. No further paid retry
was made. Proxyless operation remains weaker isolation.

A live configured memory-view smoke after PR85 exposed HTTP 404: application
composition bypassed the existing SDK-aware memory factory and sent SQL to the
Agent Memory endpoint. SDK authentication itself had succeeded earlier. This is a
composition defect, not evidence that new credentials are needed.

### ElevenLabs configured voice smoke (2026-10-16)

Read the existing authorized agent through the official agent endpoint and saved
its configured TTS voice ID in ignored `.env.local`. The existing ElevenLabs
adapter smoke returned a `wss` signed conversation URL and 26,374 audio bytes
for the short synthetic smoke phrase. This verifies actual TTS and signed URL
creation, not a dashboard conversational client or evidence Q&A session.

```bash
RUN_LIVE_INTEGRATIONS=1 .venv/bin/python -m dotenv -f .env.local run --no-override -- .venv/bin/python scripts/smoke_adapters.py elevenlabs
```

### Registered GitHub PR → hosted Gate (2026-10-16)

Supersedes the earlier unresolved PNG-only capture result: verified PNG/JPEG
container handling now stores Anchor's actual JPEG with matching media type.
GitHub PR #87, on dedicated `demo/cartwheel-base` / `demo/cartwheel-help`
fixture branches, delivered a signed webhook and executed run
`gh-2c202ade18efc1e4af86`. Actual Daytona and proxyless Anchor execution reproduced
the blocked action on head 2/2, base 0/2; the independent oracle classified it
`confirmed_regression`, attribution `introduced`. The planner was explicitly
scripted, not a live model; the UI labels this mixed evidence. Check run
117095925152 completed with expected `failure` on the exact executed head.

Headless Chrome loaded all four hosted screenshots on the run page. Evidence:
`/tmp/gauntlet-pr87-run.json`, `/tmp/gauntlet-pr87-dashboard.png`, and ignored
`artifacts/pr87-hosted-demo`. Read-only cleanup inventory confirmed zero Daytona
sandboxes and zero Anchor sessions. Anchor `list_sessions` returned HTTP 500;
`get_all_sessions_status` succeeded with count 0. No additional hosted retry.
The run reported zero memory facts written, so this is not evidence of a successful
live memory write. The UI repair plan is a labeled sample, not a hosted repair.

MAIN validation: 918 Python tests passed, 4 skipped; Ruff and mypy (168 files)
passed; wheel/sdist and dashboard production build/typecheck passed; dashboard
21 tests passed; headless rehearsal 12/12 passed in 8 seconds. Commands:

```bash
uv run --frozen --group live-providers pytest -q
uv run --frozen --group live-providers ruff check services/gauntlet scripts
uv run --frozen --group live-providers mypy services/gauntlet/src
uv build --package gauntlet-control --out-dir /tmp/gauntlet-combined-build
npm run test --prefix apps/dashboard
npm run build --prefix apps/dashboard
npm run typecheck --prefix apps/dashboard
.venv/bin/python scripts/demo_rehearsal.py --chromium '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --backup-dir /tmp/gauntlet-combined-rehearsal
```

The local API on port 8002 was launched for this bounded test with live providers,
scripted planning, and the existing registration file. Dashboard is port 3000.
Persistent `.env.local` still defaults live integration off. Restarting this
process loses its in-memory run views and dedup reservations; saved evidence
remains on disk. Arbitrary project PRs are still ignored by the fixture guard.

### P3 UI proposal and local repair runner (2026-10-16)

One real AWS Bedrock `ModelFixProposer` call used the captured PR87 finding,
frozen attack, and cited head source. It proposed changing Help CSS bottom16px
to96px. Its hunk header declared7 context lines but contained6; review corrected
only the header before `git apply --check` passed. Raw and reviewed plans are
saved in ignored `artifacts/pr87-hosted-demo/ui-fix-plan-raw-model.json` and
`ui-fix-plan.json`. Reviewed approval hash:
`1f2fddf49747545220ccd84c3df146e276f02695da8a4ede4f6260d6dfa4b086`.
The actual model proposal is **not applied** and awaits human hash approval.

The original hosted run and artifacts were restored from saved local evidence
for the development API, with that reviewed proposal attached. The temporary
bootstrap is `/tmp/gauntlet-serve-ui-review.py`; port8002 serves it, dashboard
port3000. This session bootstrap does not provide durable production storage.
It makes no new hosted browser or model calls. Persistent live integration stays
OFF; dependency cache configured at `/tmp/gauntlet-c-cartwheel-base/node_modules`.

An independent automated scripted-plan smoke exercised the new repair runner
against a real fresh Next build and real local Chrome. This is a synthetic test
approval, **not human approval of the model plan**. Patched test SHA
`cb080fd8a3b340717a8bbca314391baa64e5966f`: original attack,390px/1280px variants,
and legitimate action passed; Help opened/closed and checkout produced a receipt
at375px and1280px. Eight trusted replay attempts stored evidence. Temporary
server/export cleaned by the runner. Report `/tmp/gauntlet-ui-repair-smoke.json`,
evidence `/tmp/gauntlet-ui-repair-smoke-artifacts`. Initial real-build smoke
correctly reported not_verified because the shared exporter required refund
files; UI-specific required paths fixed that defect before the passing run.

MAIN checks after integration:
- `uv run --frozen --group live-providers pytest -q`:945 passed,4 skipped.
- `uv run --frozen --group live-providers ruff check services/gauntlet scripts`:pass.
- `uv run --frozen --group live-providers mypy services/gauntlet/src`:171 files pass.
- `uv build --package gauntlet-control --out-dir /tmp/gauntlet-ui-main-build`:wheel/sdist pass.
- `npm run test --prefix apps/dashboard`:21 pass.
- `npm run build --prefix apps/dashboard`:pass.
- `npm run typecheck --prefix apps/dashboard`:pass.
- `.venv/bin/python scripts/demo_rehearsal.py --chromium '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --backup-dir /tmp/gauntlet-ui-main-rehearsal`:12/12 pass.

Headless Chrome confirmed the saved real run displays the reviewed96px diff and
approval/apply controls. Screenshot `/tmp/gauntlet-ui-proposal-dashboard.png`.
No human approval was synthesized and no original/model patch was executed.

After integrating teammate PR88 memory changes, the full MAIN Python suite was
rerun:946 passed,4 skipped (125.22s). Ruff/mypy171 and wheel/sdist build also
passed again. This merge was reviewed for overlap; it does not claim a new live
Agent Memory smoke in this UI repair task.

### Approved model UI patch verified (2026-10-16)

User explicitly approved reviewed plan
`1f2fddf49747545220ccd84c3df146e276f02695da8a4ede4f6260d6dfa4b086`.
Authenticated `POST /approvals` returned201; `POST
/gate/runs/gh-2c202ade18efc1e4af86/repair` returned200 and
`fix_verified_review_required`. Approval ID
`approval-61637c53907246e0a5e2ba521c2e1435`; patched synthetic commit
`bb544cd2fc449669245c9f055b0d6f4eea44a2b5`. Actual Git diff changes only
`src/components/FloatingHelp.module.css`, bottom16px to96px, one line.

Real fresh local Next build and headless Chromium verified original replay2/2,
390px variant2/2,1280px variant2/2, legitimate replay2/2, and Help open/close plus
checkout receipt on both mobile and desktop. All six reported checks passed.
The repair API serves16 PNG screenshots; independent review checked every image,
recomputed the exact plan hash, checked the authenticated approval and event
ordering, and inspected the actual Git diff. No additional model or hosted
browser calls were needed. Local temporary build/server resources were cleaned.

Saved result `artifacts/pr87-hosted-demo/ui-repair-result.json`, approval
`ui-approval.json`, screenshots `approved-repair/`; dashboard at
`http://localhost:3000/gate/runs/gh-2c202ade18efc1e4af86`. Original hosted regression
remains visible above the successful repair result. Local patch was not pushed,
merged into the target branch, or deployed. This is local Chrome repair proof,
not hosted Anchor repair proof. No source-code change accompanied this execution;
prior main verification remains946 Python tests,21 dashboard tests and passing
builds. The session restoration script also reads saved repair results now.
