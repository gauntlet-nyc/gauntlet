# Local infrastructure (owner C)

`docker-compose.yml` runs SurrealDB core (in-memory) and a synthetic Postgres, bound to 127.0.0.1, with pinned image tags. Run with `docker compose --env-file .env.local -f infra/local/docker-compose.yml up`.

Status: images are pinned by tag **and** registry index digest (checked against the registries 2026-10-15). Person B ran a real Compose smoke on #2: both images pulled, SurrealDB `/health` and authenticated SQL returned HTTP 200, and Postgres accepted a cartwheel query. B used host port 15432 in a temporary copy because another local container owned 5432; the committed port is unchanged. Do not run reset scripts against anything other than an explicitly identified synthetic database. Production targets are not allowed by developer tooling.
