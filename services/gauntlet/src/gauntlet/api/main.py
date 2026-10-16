"""API composition root. Routes stay thin; Gate/Recall logic belongs to A/B packages."""

from fastapi import FastAPI

from .routes import approvals, fake_run, gate, health, offline_gate, recall, sponsors, targets


def create_app() -> FastAPI:
    app = FastAPI(title="Gauntlet Unified API", version="0.1.0")
    app.include_router(health.router)
    app.include_router(fake_run.router)
    app.include_router(targets.router)
    app.include_router(offline_gate.router)
    app.include_router(gate.router)
    app.include_router(recall.router)
    app.include_router(approvals.router)
    app.include_router(sponsors.router)
    return app


app = create_app()
