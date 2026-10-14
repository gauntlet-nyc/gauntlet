# Codex — Gauntlet v3

**Obey `AGENTS.md`; do not maintain a competing policy here.** Read `docs/DEVELOPMENT_PLAN.md` and `docs/OWNERSHIP.md` before acting. Announce owner (A/B/C), phase and explicit path allowlist before writing code. Implement only the assigned ticket in one worktree.

Prefer minimal diffs and focused tests. Source contract schemas must originate in A-owned Pydantic DTOs and be generated, not manually forked. Validate external APIs against pinned docs and actual smoke responses. If B/C needs a contract change, submit a proposal/ADR rather than editing A's DTOs. If validation fails, report the actual error and stop at the phase gate.

No keys in source, no production targets, no arbitrary model-generated shell commands, no private benchmark truth available to attackers, no model-only confirmed bugs, no historical causality claims without control replays. Report exact files/tests/limitations when finished.
