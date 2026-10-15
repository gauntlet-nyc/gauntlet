"""API composition root. Routes stay thin; Gate/Recall logic belongs to A/B packages."""

from fastapi import FastAPI

from .routes import fake_run, health, offline_gate


def create_app() -> FastAPI:
    app = FastAPI(title="Gauntlet Unified API", version="0.1.0")
    app.include_router(health.router)
    app.include_router(fake_run.router)
    app.include_router(offline_gate.router)
    return app


app = create_app()
