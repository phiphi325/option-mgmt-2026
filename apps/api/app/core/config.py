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

Versioning consolidation (M1.24):
  - `engine_version` defaults to `engine.version.__version__`. Previously this
    carried a literal default (`"0.0.0"` originally; drifted to `"1.4.0"` via
    earlier edits and silently stayed behind the engine package).
  - `weights_version` defaults to `engine.confidence.DEFAULT_WEIGHTS.version`.
    Same drift class.
  - Env vars (`ENGINE_VERSION` / `WEIGHTS_VERSION`) still override the defaults
    for rare cases (e.g. deliberate stamping with a hot-fixed version). In
    normal operation, the engine package is the source of truth.
"""

from __future__ import annotations

from functools import lru_cache

from engine.confidence import DEFAULT_WEIGHTS as _DEFAULT_WEIGHTS
from engine.version import __version__ as _engine_version
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings loaded from environment / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Versioning surfaced via /version (plan §5).
    api_version: str = "0.0.1"
    # M1.24: sourced from the engine package; env var still overrides.
    # `_engine_version` is lowercase to satisfy ruff N812 (aliasing the
    # lowercase __version__ symbol); `_DEFAULT_WEIGHTS` stays uppercase to
    # satisfy ruff N811 (aliasing a constant). Mixed casing is intentional.
    engine_version: str = _engine_version
    weights_version: str = _DEFAULT_WEIGHTS.version
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
