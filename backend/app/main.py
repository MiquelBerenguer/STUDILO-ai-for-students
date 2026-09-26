from __future__ import annotations

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.routers import activity, auth, exams, feed, notes, onboarding, settings, setup, uploads
from app.config.brand import get_brand
from app.config.models_config import ConfigError
from app.config.settings import get_settings
from app.db.engine import get_engine
from app.orchestrator.worker import Orchestrator
from app.startup import run_migrations, validate_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    s = get_settings()
    try:
        validate_settings(s)
    except ConfigError as exc:
        print(f"\n[{get_brand().name}] Configuration error — refusing to start:\n{exc}\n", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
    run_migrations()
    orchestrator = Orchestrator() if s.ENABLE_BACKGROUND else None
    if orchestrator:
        orchestrator.start()
    yield
    if orchestrator:
        await orchestrator.stop()


def create_app(with_lifespan: bool = True) -> FastAPI:
    app = FastAPI(title=f"{get_brand().name} API", version="1.0.0", lifespan=lifespan if with_lifespan else None)
    for r in (auth.router, setup.router, uploads.router, notes.router, exams.router, activity.router,
              settings.router, feed.router, feed.public, onboarding.router):
        app.include_router(r, prefix="/api/v1")

    @app.get("/api/v1/health", tags=["system"])
    def health() -> JSONResponse:
        try:
            with get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
                conn.execute(text("SELECT vec_version()"))
        except Exception as exc:  # health must report, not raise
            return JSONResponse({"status": "unhealthy", "db": str(exc)[:200]}, status_code=503)
        return JSONResponse({"status": "ok", "db": "ok"})

    return app


app = create_app()
