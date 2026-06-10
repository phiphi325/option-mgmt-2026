"""OM-Y3 smoke tests — trend-series ingest + panel reads + HTTP endpoint (live PG).

Run against the real Postgres + uvicorn in the CI smoke job (migrated via
`alembic upgrade head`, which includes `0005_yearline_trend_series`). Skipped
when SMOKE_API_URL is unset.

Covers:
  1. trend-series ingest idempotency (inserted / unchanged / updated).
  2. panel display reads: latest context (raw, incl. stale) + latest series.
  3. the `GET /engine/yearline-context` HTTP round-trip with a minted JWT.

Synthetic ticker `MSFT_YLN3` avoids colliding with the OM-Y2 smoke fixtures.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.security import create_access_token
from app.jobs.ingest_yearline import (
    ingest_yearline_context,
    ingest_yearline_trend_series,
)
from app.services.yearline_panel_service import (
    read_latest_trend_series,
    read_latest_yearline_context,
)

SMOKE_API_URL = os.environ.get("SMOKE_API_URL")
DATABASE_URL = os.environ.get("DATABASE_URL")

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        not SMOKE_API_URL,
        reason="SMOKE_API_URL not set; OM-Y3 smoke tests need a live API + DB.",
    ),
]

_FIXTURES = Path(__file__).parent / "fixtures" / "yearline"
_TICKER = "MSFT_YLN3"


def _ctx() -> dict[str, Any]:
    raw: dict[str, Any] = json.loads((_FIXTURES / "fixture_msft_gated.json").read_text())
    raw["ticker"] = _TICKER
    return raw


def _series() -> dict[str, Any]:
    raw: dict[str, Any] = json.loads(
        (_FIXTURES / "fixture_msft_trend_series.json").read_text()
    )
    raw["ticker"] = _TICKER
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
            text("DELETE FROM yearline_trend_series WHERE ticker = :t;"), {"t": _TICKER}
        )
        await session.execute(
            text("DELETE FROM yearline_context WHERE ticker = :t;"), {"t": _TICKER}
        )
        await session.commit()


@pytest.fixture(autouse=True)
async def _around() -> AsyncIterator[None]:
    await _cleanup()
    yield
    await _cleanup()


async def test_trend_series_ingest_is_idempotent() -> None:
    async with _session() as session:
        first = await ingest_yearline_trend_series(session=session, artifact=_series())
        assert first.status == "inserted"

        again = await ingest_yearline_trend_series(session=session, artifact=_series())
        assert again.status == "unchanged"

        changed = _series()
        changed["n"] = (changed["n"] or 0) + 0  # same n; mutate a value array instead
        changed["close"] = [*(changed["close"] or [])]
        if changed["close"]:
            changed["close"][0] = changed["close"][0] + 1.0
        updated = await ingest_yearline_trend_series(session=session, artifact=changed)
        assert updated.status == "updated"


async def test_panel_reads_return_latest_context_and_series() -> None:
    async with _session() as session:
        await ingest_yearline_context(session=session, artifact=_ctx())
        await ingest_yearline_trend_series(session=session, artifact=_series())

        context = await read_latest_yearline_context(session=session, ticker=_TICKER)
        series = await read_latest_trend_series(session=session, ticker=_TICKER)

    assert context is not None and context.ticker == _TICKER
    assert series is not None and series.available is True
    assert series.ticker == _TICKER


async def test_get_yearline_context_endpoint_round_trip() -> None:
    async with _session() as session:
        await ingest_yearline_context(session=session, artifact=_ctx())
        await ingest_yearline_trend_series(session=session, artifact=_series())

    token = create_access_token(subject="00000000-0000-0000-0000-0000000000y3")
    assert SMOKE_API_URL
    resp = httpx.get(
        f"{SMOKE_API_URL}/engine/yearline-context",
        params={"ticker": _TICKER},
        headers={"Authorization": f"Bearer {token}"},
        timeout=10.0,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ticker"] == _TICKER
    assert body["context"] is not None
    assert body["context"]["repair_active"] is True
    assert body["trend_series"] is not None
    assert body["trend_series"]["available"] is True
