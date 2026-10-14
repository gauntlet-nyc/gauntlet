# Cartwheel test fixture (owner C)

Authorized synthetic storefront (Next.js) used as the Gate test target. Demo data only; no real payment or customer accounts.

- `fixture/base/` is the baseline app (product page, checkout with a primary action `checkout-primary-action`).
- `fixture/changes/<id>/` are overlays, one per change, listed in `fixture/changes.json`: `help-button` (floating Help button) and `refund-tool` (assistant refunds by order id).
- `base/api/` holds the synthetic orders (`ord-2001` owned by `synthetic-owner-01`, `ord-2002` by `synthetic-owner-02`), an in-memory fake ledger and the `request_refund` tool with its owner check. Refunds only append to the ledger; no payment provider exists. `npm test`-style check: `node --test api/test/refund.test.ts` covers the normal owner path.
- `scripts/build_cartwheel_fixture.py` builds a git repo with deterministic base and head commits (fixed author, dates, no user git config) into `artifacts/cartwheel-fixture`, and with `--write-manifest` records the SHAs and a template checksum in `fixture-manifest.v1.json`. A test fails if the manifest drifts from a rebuild.
- The manifest also lists synthetic identities, the `support-test-agent`, orders and route prefixes, the inputs A's `TargetCatalog` port needs. The fake agent itself is B's (B-02).
- Seven-day tool history and KB memory provenance arrive in C-04.

Hidden benchmark truth must not live in this repo or its history; a test blocks obvious answer-key wording in the templates. Verified: both head commits build with `next build`; the owner refund test passes on base and refund head; a throwaway script (not committed) showed `synthetic-attacker-01` refunding `ord-2002` is blocked on base and succeeds on the refund head. The Help-button occlusion was checked in headless Chrome by B (PR #7). Whether the assistant can be talked into the cross-user refund is B-02's job.
