# SDK integration validation checklist — B owns

**Status: all live smokes NOT RUN in starter.** Record installed SDK version, exact API call, invocation environment, sanitized output/trace ID, elapsed time, cleanup result and SDK doc URL. Never commit keys. Package APIs and feature entitlements may change.

| Provider | Required live smoke | Known docs | Recorded result |
|---|---|---|---|
| Daytona | create sandbox, execute, access preview, optionally eligible VM fork, destroy | https://www.daytona.io/docs/en/python-sdk/ | NOT RUN |
| Anchor | create cloud session, resize, inspect, click approved preview, capture recording, close | https://github.com/anchorbrowser/AnchorBrowser-SDK-Python | NOT RUN |
| Arize AX | `arize.otel.register`, correlated span visible in AX, one actual evaluated experiment | https://arize.com/docs/ax/quickstarts/quickstart-write-first-eval | NOT RUN |
| SurrealDB core | AsyncSurreal connect, param insert/query, relation, update and close | https://surrealdb.com/docs/reference/python/api/core/surreal | NOT RUN |
| SurrealDB Agent Memory | separate context `remember`, `recall` and `as_of`/provenance query | https://surrealdb.com/docs/agent-memory/integrations/sdks/python | NOT RUN |
| AWS Bedrock | invoke approved configured model with bounded tool/JSON output | https://docs.aws.amazon.com/boto3/latest/reference/services/bedrock-runtime/client/converse.html | NOT RUN |
| ElevenLabs | authenticated evidence webhook call and private-voice conversation | https://elevenlabs.io/docs/eleven-agents/libraries/python | NOT RUN |

**SDK notes:** Daytona's VM sandbox supports `fork()`; container sandboxes require snapshot/recreation. Agent Memory is prerelease and separate from core SurrealDB DB SDK. Bedrock model IDs/availability vary by region/account. Anchor browser runs in cloud and cannot reach localhost without approved preview/tunnel. Arize is evaluation visibility, not the trusted oracle.

**Record format:** `Date / owner / provider / pinned version / test SHA / command (no tokens) / raw sanitized result / failure / fallback / next verification`.

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
- `UIWorker` bounds actions/runtime and closes the session on success, failure, timeout, and cancellation. It never assigns a Gate verdict.

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

This is a directed local diagnostic, not blind planner discovery or Daytona /
Anchor proof. The fixture has no order-submission handler, so results establish
DOM click delivery only. Keyboard fallback, fixture runtime state checksums,
legitimate order completion, and an unrelated clean PR remain P1 gates. The
temporary fixture install reported two dependency advisories; C owns dependency
review and lock changes.

### Handoff and remaining gates

- C composes the B adapters into the real API; this branch does not change C's API/dashboard or generated contracts.
- A plus another appropriate owner must review the oracle/evidence boundary; shared changes require the repository's A/B/C review.
- Full main-tree integration tests/build happen after reviewed merges. A/B/C branches remain open; branch-local success does not complete that gate.
- Repository-wide Ruff currently reports the existing C-owned `test_api.py` import ordering. Format check reports the two existing master-plan Markdown code blocks. B-owned Python lint/format and whole-source mypy are checked separately; these baseline failures are not silently fixed across ownership boundaries.
- Live provider setup requires C-approved pinned SDK dependencies, explicit `RUN_LIVE_INTEGRATIONS=1` opt-in and permitted spend, an authorized target/fixture, Daytona key/endpoint and runtime quota, Anchor key and reachable allowlisted preview, Arize key/space/project, Surreal core URL/namespace/database/auth, separate Memory endpoint/context/key/scopes, and AWS credential chain/region/model access. These prerequisites are phase-specific; B-00 requires no provider credentials.
