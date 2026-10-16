# Cartwheel build identity receipt

The synthetic Cartwheel app exposes `GET /api/build-info` from each compiled
Next production build:

```json
{"schema_version":"1.0","source_sha":"e5ab64c85d3080b2982c68da23ab677ce8cb5a69"}
```

`source_sha` is the full lowercase Git HEAD SHA of the generated fixture repo
used for that build. The response sends `Cache-Control: no-store, max-age=0`.
The route is dynamic. If the compiled identity is missing or malformed, it
returns HTTP 503 without claiming a revision.

`next.config.js` derives the SHA with fixed Git commands and rejects a dirty
checkout, including untracked source files. It rejects an externally supplied
`CARTWHEEL_BUILD_SOURCE_SHA`. Next embeds the value in the compiled route;
the route does not run Git or read a mutable SHA from the runtime environment.
Build the generated base or head checkout separately after committing any
source change. The template directory itself is not a standalone fixture repo.

This is a receipt from a trusted synthetic fixture build. It does not attest
to malicious source code, the container image, a deployed server's network
identity, or the fixture state. A consumer must still match the receipt to the
registered revision and verify the rest of the environment independently.

Next's [config `env` documentation](https://nextjs.org/docs/15/pages/api-reference/config/next-config-js/env)
specifies build-time replacement of direct `process.env` references.
