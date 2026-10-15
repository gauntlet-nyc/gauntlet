# Local infrastructure (owner C)

`docker-compose.yml` runs SurrealDB core (in-memory) and a synthetic Postgres, bound to 127.0.0.1, with pinned image tags. Run with `docker compose --env-file .env.local -f infra/local/docker-compose.yml up`.

Status: written but **not yet started or validated** (image tags unverified against the registries). Tags are not digests; pin digests once pulled. Do not run reset scripts against anything other than an explicitly identified synthetic database. Production targets are not allowed by developer tooling.
