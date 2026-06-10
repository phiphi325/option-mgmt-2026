"""Yearline context hydration service (OM-Y2).

Reads the latest persisted `yearline_context` row back into the engine's frozen
`engine.yearline.YearlineContext` value object — mirroring how
`inputs_hydration_service` hydrates MarketState / FlowScore.

Per ADR-0009 + docs/enhancements/0002-yearline-context-assessment.md.

**Graceful abstention (the gate-respect rule on the hydration boundary).** This
returns `None` — "no usable context" — when:
  - no row exists for the ticker (artifact never ingested), OR
  - the latest row's payload is `is_stale: true` (the producer's freshness flag), OR
  - `max_age_days` is set and the row's `as_of` is older than that window.

`None` flows straight into the engine's optional `yearline_context` kwarg (OM-Y4),
so a missing/stale context degrades gracefully to the pre-yearline decision —
exactly like the `futures_basis=0` stub. OM-Y3's read-only panel may instead read
the raw row to *show* staleness honestly; this engine-facing path abstains.

## Public API

  hydrate_yearline_context(*, session, ticker, as_of=None, max_age_days=None)
      -> YearlineContext | None
"""

from __future__ import annotations

from datetime import date

from engine.yearline import YearlineContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_LATEST_SQL = text(
    """
    SELECT payload, as_of
    FROM yearline_context
    WHERE ticker = :ticker
      AND (CAST(:as_of AS date) IS NULL OR as_of <= CAST(:as_of AS date))
    ORDER BY as_of DESC
    LIMIT 1;
    """
)


async def hydrate_yearline_context(
    *,
    session: AsyncSession,
    ticker: str,
    as_of: date | None = None,
    max_age_days: int | None = None,
) -> YearlineContext | None:
    """Return the latest usable `YearlineContext` for `ticker`, else `None`.

    Args:
        session:      Async SQLAlchemy session.
        ticker:       Underlying symbol (e.g. "MSFT").
        as_of:        Upper bound on the row's data date. When None, the most
                      recent row wins. Bounding by the decision's `as_of`
                      preserves replay determinism (no peeking at future data).
        max_age_days: When set, a row whose `as_of` is more than this many days
                      before the effective `as_of` is treated as stale → `None`.

    Returns:
        A parsed `YearlineContext`, or `None` for missing / stale / too-old.
    """
    result = await session.execute(
        _LATEST_SQL,
        {"ticker": ticker, "as_of": as_of.isoformat() if as_of is not None else None},
    )
    row = result.first()
    if row is None:
        return None

    payload, row_as_of = row[0], row[1]
    ctx = YearlineContext.model_validate(payload)

    # The producer's own freshness flag → honest abstention.
    if ctx.is_stale:
        return None

    # Optional run-date freshness window (the handoff's "re-check as_of vs your
    # run date"). `row_as_of` is a `date` from the DATE column.
    if max_age_days is not None and isinstance(row_as_of, date):
        reference = as_of if as_of is not None else date.today()  # noqa: DTZ011
        if (reference - row_as_of).days > max_age_days:
            return None

    return ctx


__all__ = ["hydrate_yearline_context"]
