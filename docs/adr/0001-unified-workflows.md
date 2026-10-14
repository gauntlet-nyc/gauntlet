# ADR 0001 — Gate and Recall share a replay engine, not verdict rules

**Status:** Proposed for A/B/C acceptance

## Context

Gauntlet v2 describes adaptive pre-merge software testing. The combined original design adds historical refund auditing. True Agent Recall also replays recorded agent decisions without a poisoned source. These share isolation/evidence but differ in inputs and correctness conditions.

## Decision

Use a modular Python backend with separate `application/gate` and `application/recall` workflows. Shared `ReplaySpec` and sandbox/execution ports support Gate base/head, historical operation audit, control/counterfactual, and post-fix regression. Each workflow has separate adjudication and verdict enum. SurrealDB core is event/lineage store, SurrealDB Agent Memory a separate typed temporal service. Human approval gates apply to patch plans and real-world remediation.

## Alternatives

One giant universal agent was rejected: oracle attribution and replay semantics become easy to conflate. Separate microservices were deferred: unnecessary deployment/network coordination for a three-person team. Historical log searching alone as "counterfactual" was rejected because it cannot establish changed agent decisions.

## Consequences

Requires additional typed contracts and coverage/replay manifests; keeps genuine historical limitations visible. Model provider and external SDKs remain behind independent adapters. Users cannot assume unlogged historical inputs are reconstructable.

## Rollback

Gate functions without Recall by disabling its route/worker registry. Historical recorder and memory schema changes need forward-only migration strategy.

## Review

A: pending / B: pending / C: pending
