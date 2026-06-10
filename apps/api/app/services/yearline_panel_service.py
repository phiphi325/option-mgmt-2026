"""Display reads for the yearline evidence panel (OM-Y3).

Distinct from `yearline_hydration_service` (the engine-facing path that
*abstains* on stale, used by OM-Y4): these reads return the **raw latest** rows
so the read-only panel can show staleness honestly (UX §6.5). They never feed a
decision.

  read_latest_yearline_context(...)    -> YearlineContext | None
  read_latest_trend_series(...)        -> YearlineTrendSeriesModel | None
"""

from __future__ import annotations

from datetime import date

from engine.yearline import YearlineContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.yearline import YearlineTrendSeriesModel

_CONTEXT_SQL = text(
    """
    SELECT payload
    FROM yearline_context
    WHERE ticker = :ticker
      AND (CAST(:as_of AS date) IS NULL OR as_of <= CAST(:as_of AS date))
    ORDER BY as_of DESC
    LIMIT 1;
    """
)

_TREND_SQL = text(
    """
    SELECT payload
    FROM yearline_trend_series
    WHERE ticker = :ticker
      AND (CAST(:as_of AS date) IS NULL OR as_of <= CAST(:as_of AS date))
    ORDER BY as_of DESC
    LIMIT 1;
    """
)


async def read_latest_yearline_context(
    *,
    session: AsyncSession,
    ticker: str,
    as_of: date | None = None,
) -> YearlineContext | None:
    """Latest persisted context for display — returned even when `is_stale`."""
    result = await session.execute(
        _CONTEXT_SQL,
        {"ticker": ticker, "as_of": as_of.isoformat() if as_of is not None else None},
    )
    row = result.first()
    if row is None:
        return None
    return YearlineContext.model_validate(row[0])


async def read_latest_trend_series(
    *,
    session: AsyncSession,
    ticker: str,
    as_of: date | None = None,
) -> YearlineTrendSeriesModel | None:
    """Latest persisted (`available`) trend series for display, or `None`."""
    result = await session.execute(
        _TREND_SQL,
        {"ticker": ticker, "as_of": as_of.isoformat() if as_of is not None else None},
    )
    row = result.first()
    if row is None:
        return None
    return YearlineTrendSeriesModel.model_validate(row[0])


__all__ = ["read_latest_trend_series", "read_latest_yearline_context"]
