# Security and trust model

**Threats:** arbitrary URL navigation/redirects, malicious source/tool/page text, path traversal, exfiltration, model tool misuse, untrusted shell/JS, hidden benchmark data leakage, mutable oracle registry, replaying historical real effects, approval/hash race, poison memory and unauthorized voice actions.

**Required controls:** server registered repository/target IDs; exact allowed preview origin and DNS/redirect validation; scoped file reads excluding `.env`, Git internals and benchmark; no secret in Daytona app sandbox/Anchor/CDP; network egress restrictions; synthetic actor fixtures; trusted oracle code physically inaccessible to fixer; hidden benchmark truth outside accessible repo; prompt/source context marked untrusted but enforced by code allowlists; step/time/token concurrency budget; cancellation cleanup.

**Historical:** instrumentation coverage certificate; replay tool results from records; simulated payment/mail effects only; redaction/retention/encryption and read-only lineage; no automatic remediation or customer contact. LLM matching policy is non-authoritative; only auditable human decisions create review approvals.

**Approval:** authenticated reviewer + run_id + exact plan_sha256 + TTL + allowed_paths; no voice approval or automatic merge. Proof bundle immutability and nonce prevent replay across patches. Production RBAC and tenant isolation are out of scope until explicitly implemented and audited.

**Tests to require:** deny outside repo/host/redirect; prevent reading benchmark truth; inability to edit trusted oracle; mismatched plan hash rejected; replay cannot call real payment/refund/email; clean teardown on cancel; sanitized Arize span and browser evidence.
