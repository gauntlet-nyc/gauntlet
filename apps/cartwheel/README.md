# Cartwheel test fixture (owner C)

Authorized synthetic storefront (Next.js) used as the Gate test target. Demo data only; no real payment or customer accounts.

- `fixture/base/` is the baseline app (product page, checkout with a primary action `checkout-primary-action`).
- `fixture/head/` is the overlay for the "Add a floating Help button" change.
- Checkout posts one fixed synthetic item to an in-process order store and displays a receipt returned by the server. `GET /api/orders/{id}` lets local tests verify the receipt. Orders disappear when the server restarts; there is no payment or durable order database.
- `scripts/build_cartwheel_fixture.py` builds a git repo with deterministic base and head commits (fixed author, dates, no user git config) into `artifacts/cartwheel-fixture`, and with `--write-manifest` records the SHAs and a template checksum in `fixture-manifest.v1.json`. A test fails if the manifest drifts from a rebuild.
- Seven-day tool history and KB memory provenance arrive in C-04. The AI-tool target (`request_refund`) arrives in C-02.

Hidden benchmark truth must not live in this repo or its history; a test blocks obvious answer-key wording in the templates. The local headless diagnostic now exercises actual Checkout clicks and verifies server receipts on the base and at desktop width on the head. These local results do not replace B's independent oracle or Daytona/Anchor run.
