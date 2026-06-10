"""OM-Y2 smoke tests — yearline ingest idempotency + hydration (live Postgres).

Run against the real Postgres in the CI smoke job (migrated via `alembic upgrade
head`, which includes `0004_yearline_context`). Skipped when SMOKE_API_URL is
unset (the same gate the other smoke suites use — it signals "live DB present").

These exercise the DB-backed paths the unit tests can't:
  1. ingest → `inserted`; re-ingest identical bytes → `unchanged` (true no-op);
     re-ingest changed bytes for the same (ticker, as_of) → `updated`.
  2. hydrate returns the parsed YearlineContext for a fresh, non-stale row.
  3. hydrate returns None for a stale row (is_stale) and for a missing ticker.

Synthetic tickers (`*_YLN*`) avoid colliding with other smoke fixtures.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.jobs.ingest_yearline import ingest_yearline_context
from app.services.yearline_hydration_service import hydrate_yearline_context

SMOKE_API_URL = os.environ.get("SMOKE_API_URL")
DATABASE_URL = os.environ.get("DATABASE_URL")

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        not SMOKE_API_URL,
        reason="SMOKE_API_URL not set; OM-Y2 smoke tests need a live DB (CI smoke job).",
    ),
]

_FIXTURES = Path(__file__).parent / "fixtures" / "yearline"
_TICKER = "MSFT_YLN"
_STALE_TICKER = "MSFT_YLN_STALE"
_MISSING_TICKER = "MSFT_YLN_NONE"


def _gated() -> dict[str, Any]:
    raw: dict[str, Any] = json.loads((_FIXTURES / "fixture_msft_gated.json").read_text())
    raw["ticker"] = _TICKER
    return raw


def _stale() -> dict[str, Any]:
    raw: dict[str, Any] = json.loads((_FIXTURES / "fixture_stale_empty.json").read_text())
    raw["ticker"] = _STALE_TICKER
    return raw


@asynccontextmanager
async def _session() -> AsyncIterator[AsyncSession]:
    assert DATABASE_URL
    engine = create_async_engine(DATABASE_URL, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as session:
            yield session
    finally:
        await engine.dispose()


async def _cleanup() -> None:
    async with _session() as session:
        await session.execute(
            text("DELETE FROM yearline_context WHERE ticker = ANY(:tickers);"),
            {"tickers": [_TICKER, _STALE_TICKER, _MISSING_TICKER]},
        )
        await session.commit()


@pytest.fixture(autouse=True)
async def _around() -> AsyncIterator[None]:
    await _cleanup()
    yield
    await _cleanup()


async def test_ingest_is_idempotent_insert_unchanged_update() -> None:
    async with _session() as session:
        first = await ingest_yearline_context(session=session, artifact=_gated())
        assert first.status == "inserted"
        assert first.ticker == _TICKER
        assert first.as_of == "2026-05-29"

        again = await ingest_yearline_context(session=session, artifact=_gated())
        assert again.status == "unchanged"
        assert again.payload_hash == first.payload_hash

        changed = _gated()
        changed["distance_to_ma250_pct"] = -9.999
        updated = await ingest_yearline_context(session=session, artifact=changed)
        assert updated.status == "updated"
        assert updated.payload_hash != first.payload_hash

    # Exactly one row for (ticker, as_of) after three ingests.
    async with _session() as session:
        count = await session.execute(
            text("SELECT COUNT(*) FROM yearline_context WHERE ticker = :t;"),
            {"t": _TICKER},
        )
        assert int(count.scalar() or 0) == 1


async def test_hydrate_returns_latest_non_stale_context() -> None:
    async with _session() as session:
        await ingest_yearline_context(session=session, artifact=_gated())
        ctx = await hydrate_yearline_context(session=session, ticker=_TICKER)
    assert ctx is not None
    assert ctx.ticker == _TICKER
    assert ctx.as_of == date(2026, 5, 29)
    assert ctx.repair_active is True
    assert ctx.gate_passed == {10: True, 20: True, 40: True, 60: True}


async def test_hydrate_abstains_on_stale_row() -> None:
    async with _session() as session:
        result = await ingest_yearline_context(session=session, artifact=_stale())
        assert result.status == "inserted"
        ctx = await hydrate_yearline_context(session=session, ticker=_STALE_TICKER)
    assert ctx is None  # is_stale → honest abstention


async def test_hydrate_returns_none_for_missing_ticker() -> None:
    async with _session() as session:
        ctx = await hydrate_yearline_context(session=session, ticker=_MISSING_TICKER)
    assert ctx is None
