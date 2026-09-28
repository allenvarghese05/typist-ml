"""FastAPI app factory (design doc sections 6 and 14). `just dev` runs it with uvicorn --factory."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from importlib.metadata import version

from fastapi import FastAPI
from sqlalchemy import Engine

from typist.api.routers import health
from typist.config import Settings, get_settings
from typist.db import create_db_engine

API_PREFIX = "/api/v1"


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Dispose of the engine's pooled connections when the server stops."""
    yield
    engine: Engine = app.state.engine
    engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API app. uvicorn calls it with no arguments; tests pass their own Settings.

    - Every endpoint is JSON under /api/v1. The Vite dev server proxies /api here, so there is no
      CORS middleware (T0.2 owner answer 16; D21 amendment).
    - /docs and /redoc are disabled because they load third-party CDN assets (D19). The OpenAPI
      schema is served at /api/v1/openapi.json, so the Vite proxy forwards it too.
    - The engine for settings.db_path is created here (no connection yet) and stored on
      app.state.engine. The address (127.0.0.1:8000) is set by the caller, `just dev`.
    """
    resolved = settings if settings is not None else get_settings()
    app = FastAPI(
        title="Typist-ML API",
        version=version("typist-api"),
        docs_url=None,
        redoc_url=None,
        openapi_url=f"{API_PREFIX}/openapi.json",
        lifespan=_lifespan,
    )
    app.state.settings = resolved
    app.state.engine = create_db_engine(resolved.db_path)
    app.include_router(health.router, prefix=API_PREFIX)
    return app
