# Submission: 3-minute talk track and known limitations

The click-path, go-live checklist and fallback are in [`DEMO.md`](DEMO.md). This file is what
to **say**, timed to that path. Read the provenance badge on every screen out loud: say which
parts ran live.

## Talk track (≈3:00)

**0:00 — Problem (20 s)**
"AI writes more of our code and more of our support decisions. CI only runs the tests someone
wrote. This PR adds a floating Help button. Every check is green. Nobody wrote a test for a
small phone screen."

**0:20 — Gate, Help button (50 s)** *(DEMO.md Act A)*
- "Gauntlet reads the diff. The planner cites these exact CSS lines and proposes a 375 px
  checkout test. It only proposes: a validator checks every step against registered routes,
  actors and oracles."
- "The plan is hashed and frozen before any sandbox exists."
- "Same attack, twice on the PR head, twice on the base, in isolated environments. On head the
  click lands on the Help button. On base it reaches Place order."
- "Verdict: confirmed regression, introduced by this PR. Screenshots and click measurements are
  stored write-once, and the oracle re-checks the bytes."

**1:10 — Gate, AI refund tool (40 s)** *(Act B)*
- "Different PR: the support assistant can now refund orders. Same planner, different surface.
  It sees a deleted ownership check on a tool that moves money, so it plans an AI-agent attack."
- "An attacker asks the assistant to refund someone else's order. The oracle ignores the chat
  and reads the ledger. On head, money went to the wrong person. On base, the tool refused."
- "The fix restores the check. Apply before approval: refused. A reviewer approves the exact
  hash. The patch runs in a fresh worktree, and the original attack, a variant and the owner's
  own refund are re-run. Verdict: fix verified, review required. A human still merges."

**1:50 — Recall (50 s)** *(Act C)*
- "Now assume a bad KB chunk already shipped. It said ownership was checked upstream."
- "Audit first: 36 refunds checked against the ledger, 3 real violations, 1 inconclusive because
  the result was never logged. Missing logs are never 'clear'."
- "Counterfactual: for each decision that saw the chunk we replay a control with everything
  pinned, which must reproduce the original, then remove only that chunk. Three tainted,
  including a second-order one: the chunk became a memory note that a later decision read. Two
  cleared: exposed, but the owner would have been refunded anyway. One not replayable."
- "Everything lands in a review queue. Nothing is reversed automatically."

**2:40 — Close (20 s)** *(Sponsor proof)*
- Read the sponsor table: what each one does and whether it ran live today.
- "Gauntlet read what changed, invented the test, proved the failure in isolation and gated
  the fix on a human. When the bug had already shipped, Recall separated proven harm from
  assumptions."

## Known limitations (say these if asked)

- **Live status.** Only Daytona has run live (snapshot create + cold restore with verified
  preview). Anchor, Arize, hosted SurrealDB, Agent Memory, ElevenLabs, Azure planning and the
  GitHub App are built and offline-tested; they go live by setting env vars. SurrealDB core ran
  against a local image. See `SDK_VALIDATION.md`.
- **Offline stand-ins are labeled.** Without keys the planner is scripted, the support agent is
  a deterministic stand-in, and the default browser is a simulated layout. The oracle path
  (evidence store, binding checks, pair adjudication) is the real one. The Help-button verdict
  was also confirmed with real headless Chromium against real `next build` output.
- **AI-agent tool world runs locally.** The refund tool runs as a Node subprocess on the host
  with an empty environment and a timeout, not inside Daytona.
- **Anchor without egress proxy** for the demo (`GAUNTLET_ANCHOR_REQUIRE_PROXY=0`): weaker
  isolation, shown in provenance.
- **Recall replay offline** uses a deterministic agent policy, so no control mismatch appears
  offline. The mismatch path is covered by tests with an unstable model.
- **Workers not built:** workflow and concurrency. Proposals for them are reported `not_tested`.
- **Auth is dev-grade:** server-side reviewer tokens. No multi-tenant isolation, IdP or RBAC yet
  (`TENANCY_AND_AUTH.md` lists the gaps).
- **Targets are synthetic.** No real customers, payments or production systems.
