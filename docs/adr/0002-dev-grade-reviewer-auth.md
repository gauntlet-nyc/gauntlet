# ADR 0002: Dev-grade reviewer authentication for the demo

**Status:** Accepted for the hackathon/demo by the team owner on PR #13. Revisit in Phase 10.

## Context
Approval routes need a reviewer identity that is never taken from a request body. No identity provider is integrated yet.

## Decision
Accept only a bearer token found in the server-side table `GAUNTLET_REVIEWER_TOKENS` (JSON: token to `{reviewer_id, channel}`). An unset or malformed table refuses every approval (401). `channel` is limited to `dashboard` or `api`; voice cannot be configured. The dashboard server holds one token in `GAUNTLET_REVIEWER_TOKEN` (never `NEXT_PUBLIC_*`).

## Alternatives
- GitHub OAuth or another identity provider: deferred to Phase 10 hardening.
- Trusting a client-supplied reviewer header or body field: rejected, it is spoofable.

## Consequences
Known limitations: tokens are static and shared secrets, there is no per-user login, rotation or revocation beyond restarting with a new table, and approval records and fix plans are held in memory and lost on restart. Not suitable for real users or real data.

## Migration
Replace `api/auth.py::authenticated_reviewer` with an identity-provider-backed dependency that returns the same `AuthenticatedReviewer`; replace `api/dev_stores.py` with B's persistence. Route code and `ApprovalService` do not change.

## Rollback
Remove the approval routes; nothing else depends on them.

## Approvers
Team owner (@rudraasakariya), recorded on PR #13. Reviewers: @rishibhansali, @moh0405.
