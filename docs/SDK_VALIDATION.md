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
