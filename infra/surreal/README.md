# SurrealDB migrations (owner B)

Use versioned SurrealDB core graph migrations; separate SurrealDB Agent Memory service client config. Implement lineage tables and indexes only after selected core DB and SDK versions verified. Query parameter binding mandatory. No direct SQL from LLM output. Test temporal `as_of` access and supersession through the separate memory API.

## Implemented (Session 2, 2026-10-16)

- `persistence/surreal_client.py`: HTTP `/rpc` client (httpx, no SDK). Fixed SurrealQL strings with typed bound variables only.
- `persistence/surreal_store.py`: `CORE_SCHEMA` (version `s2-core-1`, idempotent `DEFINE ... IF NOT EXISTS`, applied by `apply_core_schema`). Tables: `run_event` (record ID `[run_id, sequence]`, unique `(run_id, sequence)`), `lineage_node` + relation table `influences`, `decision`, `tool_event`, `schema_migration`.
- `memory/surreal_memory.py`: memory facts in a separate namespace `agent_memory`, database = `SURREAL_MEMORY_CONTEXT`, bearer token `SURREAL_MEMORY_API_KEY`. Append-only; supersession checked in a transaction.
- Verified against the pinned local image; hosted SurrealDB and the Agent Memory SDK are NOT RUN.
