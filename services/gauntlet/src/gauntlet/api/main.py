"""API composition root. Routes stay thin; Gate/Recall logic belongs to A/B packages."""

from fastapi import FastAPI

from .dev_stores import DevState
from .routes import fake_run, fix_plans, health, targets


def create_app() -> FastAPI:
    app = FastAPI(title="Gauntlet Unified API", version="0.1.0")
    app.state.dev = DevState()
    app.include_router(health.router)
    app.include_router(fake_run.router)
    app.include_router(targets.router)
    app.include_router(fix_plans.router)
    return app


app = create_app()
