# Dashboard (owner C)

Next.js 15 (App Router, strict TypeScript). Currently two routes: `/` (overview) and `/fake-run`, which renders the control API's `/runs/fake` golden output. No real Gate or Recall data exists yet. Planned routes: `/gate/[id]`, `/recall/[id]`, finding/fix review (read-only timeline, human-gated approvals).

Client types are generated from the API's OpenAPI document; never hand-copy DTOs.

```bash
PYTHONPATH=services/gauntlet/src uv run python scripts/export_openapi.py   # refresh apps/dashboard/openapi.json
pnpm --filter @gauntlet/dashboard generate:api                              # refresh src/lib/api-types.ts
uv run uvicorn gauntlet.api.main:app --port 8000                            # control API
NEXT_PUBLIC_GAUNTLET_API_URL=http://localhost:8000 pnpm --filter @gauntlet/dashboard dev
```

Checks: `pnpm --filter @gauntlet/dashboard typecheck | lint | test | build`.
