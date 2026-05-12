"""FastAPI app entry point.

Mounted under prefix `/api/v1`:
  GET  /api/v1/health, /api/v1/healthz, /api/v1/version          (M0.3, this PR)
  POST /api/v1/auth/{login,register}                              (M1.x)
  POST /api/v1/engine/{daily-plan,recommend,what-if,...}          (M1.x)
  CRUD /api/v1/{profile,outcomes}                                  (M1.x)
  POST /api/v1/data/{positions,...}/import-csv                    (M1.x)
  GET  /api/v1/market/{ticker}/latest                              (M1.x — per v1.2 §22.21)
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.routers import (
    auth,
    data_import,
    engine,
    health,
    market,
    outcomes,
    profile,
)
from app.schemas.error import ProblemDetails

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Run-once startup + shutdown hooks."""
    settings = get_settings()
    configure_logging(settings.log_level)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="MSFT Option Risk Management Engine API",
        version=settings.api_version,
        lifespan=lifespan,
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        openapi_url=f"{API_PREFIX}/openapi.json",
    )

    # CORS — Next.js (3000) by default; production origins added via env.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        problem = ProblemDetails(
            type="about:blank",
            title=exc.detail if isinstance(exc.detail, str) else "HTTP error",
            status=exc.status_code,
            detail=str(exc.detail) if not isinstance(exc.detail, str) else None,
            instance=str(request.url.path),
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=problem.model_dump(exclude_none=True),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        problem = ProblemDetails(
            type="about:blank",
            title="Internal Server Error",
            status=500,
            detail=str(exc) if settings.is_dev else None,
            instance=str(request.url.path),
        )
        return JSONResponse(
            status_code=500,
            content=problem.model_dump(exclude_none=True),
        )

    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(engine.router, prefix=API_PREFIX)
    # M1.17
    app.include_router(profile.router, prefix=API_PREFIX)
    app.include_router(outcomes.router, prefix=API_PREFIX)
    app.include_router(data_import.router, prefix=API_PREFIX)
    app.include_router(market.router, prefix=API_PREFIX)
    return app


# Module-level app for `uvicorn app.main:app`.
app = create_app()
