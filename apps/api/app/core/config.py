"""Application settings, loaded from environment.

Required env vars:
    JWT_SECRET           — must be >= 16 chars (no default)

Optional with defaults:
    DATABASE_URL         — postgresql+psycopg URL; defaults to docker-compose dev
    JWT_ALGORITHM        — defaults to HS256
    JWT_ACCESS_TOKEN_TTL — seconds; defaults to 30 days (per plan v1.2 §15)
    CORS_ORIGINS         — JSON list of allowed origins; defaults to localhost:3000
    LOG_LEVEL            — defaults to INFO
    GIT_SHA              — set by Docker build / CI; defaults to "unknown"

API_VERSION, ENGINE_VERSION, WEIGHTS_VERSION are surfaced through /version and
on every persisted DailyDecision per plan v1.2 §5.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings loaded from environment / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Versioning surfaced via /version (plan §5).
    api_version: str = "0.0.1"
    engine_version: str = "0.0.0"  # bumped when packages/engine ships in M0.6+
    weights_version: str = "v2.0"  # per v1.2 §22.13 (multiplicative-penalty Confidence Composer)
    git_sha: str = "unknown"

    # Database
    database_url: str = Field(
        default="postgresql+psycopg://postgres:dev@localhost:5432/msft_engine"
    )
    redis_url: str | None = None  # P2+

    # JWT auth
    jwt_secret: str = Field(min_length=16)
    jwt_algorithm: str = "HS256"
    jwt_access_token_ttl_seconds: int = 60 * 60 * 24 * 30  # 30 days, plan §15

    # CORS — Next.js dev on 3000 by default; production lists added via env.
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # Logging
    log_level: str = "INFO"

    @property
    def is_dev(self) -> bool:
        """Heuristic: are we running against a local dev DB?"""
        return "localhost" in self.database_url or "postgres:" in self.database_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor. Raises if required env vars are missing."""
    return Settings()  # type: ignore[call-arg]
