# Cartwheel test fixture (owner C)

Authorized synthetic storefront (Next.js) used as the Gate test target. Demo data only; no real payment or customer accounts.

- `fixture/base/` is the baseline app (product page, checkout with a primary action `checkout-primary-action`).
- `fixture/head/` is the overlay for the "Add a floating Help button" change.
- `scripts/build_cartwheel_fixture.py` builds a git repo with deterministic base and head commits (fixed author, dates, no user git config) into `artifacts/cartwheel-fixture`, and with `--write-manifest` records the SHAs and a template checksum in `fixture-manifest.v1.json`. A test fails if the manifest drifts from a rebuild.
- Seven-day tool history and KB memory provenance arrive in C-04. The AI-tool target (`request_refund`) arrives in C-02.

Hidden benchmark truth must not live in this repo or its history; a test blocks obvious answer-key wording in the templates. Verified so far: the head commit builds with `next build`. Whether the Help button actually blocks the primary action at mobile widths has **not** been tested; that is B's oracle job.
