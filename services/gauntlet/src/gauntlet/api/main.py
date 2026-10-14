"""Minimal real FastAPI healthcheck; Gate/Recall routes are Phase 0+ work."""

from fastapi import FastAPI

app = FastAPI(title="Gauntlet Unified API", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "mode": "scaffold-only", "provider_integrations": "not-implemented"}
