"""Health & version endpoints (per plan v1.2 §22.7 / §21).

  GET /health     — JSON status, uptime, db reachability, versions.
  GET /healthz    — alias of /health (legacy + k8s convention).
  GET /version    — versions only; cheap (no DB roundtrip).

Both /health and /healthz exist per v1.2 §22.7 ("New endpoints (Phase 1)" table).
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.schemas.health import HealthResponse, VersionResponse

router = APIRouter(tags=["system"])

# Process-level boot time (monotonic so it survives wall-clock changes).
_BOOT_TIME = time.monotonic()


async def _db_status(session: AsyncSession) -> str:
    """Return 'ok' if the DB responds to SELECT 1, else 'degraded'."""
    try:
        await session.execute(text("SELECT 1"))
        return "ok"
    except Exception:  # noqa: BLE001 — health endpoint must never raise
        return "degraded"


@router.get("/health", response_model=HealthResponse)
@router.get("/healthz", response_model=HealthResponse)
async def health(
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> HealthResponse:
    return HealthResponse(
        status="ok",
        uptime_seconds=int(time.monotonic() - _BOOT_TIME),
        db=await _db_status(session),
        version=settings.api_version,
        engine_version=settings.engine_version,
        weights_version=settings.weights_version,
    )


@router.get("/version", response_model=VersionResponse)
async def version(settings: Settings = Depends(get_settings)) -> VersionResponse:
    return VersionResponse(
        version=settings.api_version,
        engine_version=settings.engine_version,
        weights_version=settings.weights_version,
        git_sha=settings.git_sha,
    )
