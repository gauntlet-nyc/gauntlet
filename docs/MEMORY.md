# SurrealDB core graph and Agent Memory policy

**Two products:** SurrealDB core stores normalized immutable run/event/lineage records using the database SDK and schema migrations. SurrealDB Agent Memory is a separate context service accessed using `surrealdb.memory.AsyncMemory` (prerelease `surrealdb[memory]`), not a table hidden behind the core connection. Credential sets and adapters remain separate.

**Typed verified facts:** mechanism kind, affected code surface, known_at, valid_from/until, source finding/oracle/trace IDs, fixture/commit, verification status, trust and supersession link. Only independently confirmed replayable findings become trusted regression memory. The planner, investigator and fixer may retrieve with different lenses/permissions. Retrieved memory is untrusted context, never an oracle or authorizing instruction.

**Sponsor verification:** first write memory from a confirmed UI test; retrieve it when a related new change arrives; show provenance-backed source and plan difference with/without memory; supersede older advice and show both histories; query as-of before discovery, confirm future information absent. Maintain core graph lineage for documents/chunks/memory/decisions; hybrid similarity is investigative suggestion, not evidence of actual exposure.

**Important:** Current SurrealDB Agent Memory SDK is separately versioned/pre-release; install `uv add --prerelease=allow 'surrealdb[memory]'` only after lock/version test. See official SDK reference in master plan.
