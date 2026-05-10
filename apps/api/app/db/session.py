"""SQLAlchemy async engine + session factory.

Uses psycopg3 in async mode (`postgresql+psycopg://...`) so the same connection
URL works for both Alembic migrations (sync) and FastAPI request handlers (async).

The engine is lazily constructed via lru_cache so importing this module does
not connect to the DB or require DATABASE_URL to be set at import time
(important for tooling like alembic that imports app code).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        future=True,
    )


@lru_cache(maxsize=1)
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        get_engine(),
        expire_on_commit=False,
        class_=AsyncSession,
    )


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a fresh AsyncSession per request."""
    factory = get_session_factory()
    async with factory() as session:
        yield session
