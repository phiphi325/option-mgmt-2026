"""Response models for /health, /healthz, /version."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    uptime_seconds: int = Field(ge=0)
    db: Literal["ok", "degraded"]
    version: str
    engine_version: str
    weights_version: str


class VersionResponse(BaseModel):
    version: str
    engine_version: str
    weights_version: str
    git_sha: str
