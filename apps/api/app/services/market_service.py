"""Market service — `GET /market/{ticker}/latest` (M1.16b, deferred to M1.17).

Per plan v1.2 §7 v1.1 + §22.10 + §17 M1.17.

Builds a `MarketLatestSnapshot` by reading the most-recent rows across
`option_chain_snapshots`, `iv_history`, `hv_history`, `events` and
computing `max_pain`, `pcr_volume`, `pcr_oi`, and `expected_move_pct`
on-the-fly via engine primitives (per §22.10: "computes on the fly,
no engine pipeline call").

This endpoint is the convenience read-through powering the Today screen
header — it doesn't invoke the engine pipeline, so it's safe to call
even when no `daily_decisions` row exists yet for the user.

## Spot derivation (V1)

`option_chain_snapshots` has no per-snapshot `spot` column (§6 schema).
For V1, the service derives spot as the strike of the row with the
highest combined OI at the nearest expiry. High-OI strikes cluster near
ATM in practice. This is a heuristic — a future refinement could store
spot explicitly when uploading the chain or read from a separate
market-data table.

## Prerequisites (422 cases per §22.10)

- `iv_history` for the ticker has < 30 rows → 422 "insufficient_iv_history"
- `option_chain_snapshots` empty for ticker → 422 "chain_not_yet_ingested"

## Staleness (§22.10 thresholds)

- `chain_age_seconds > 7200`   (2h)  → tag "stale_chain", any_stale=true
- `iv_age_seconds    > 90000`  (~25h) → tag "stale_iv", any_stale=true
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from engine.market_state import (
    compute_max_pain,
)
from engine.market_state import (
    expected_move_pct as compute_expected_move_pct,
)
from engine.market_state import (
    pcr_oi as compute_pcr_oi,
)
from engine.market_state import (
    pcr_volume as compute_pcr_volume,
)
from engine.types import OptionContract, OptionType
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.market import DataFreshness, MarketLatestSnapshotResponse

# §22.10 staleness thresholds
_CHAIN_STALE_SECONDS = 7200          # 2h
_IV_STALE_SECONDS = 90000            # ~25h
_HV_STALE_SECONDS = 90000            # same as iv

# §22.12 minimum iv_history row count
_MIN_IV_ROWS = 30


async def get_market_latest_snapshot(
    *,
    session: AsyncSession,
    ticker: str,
    as_of: datetime | None = None,
) -> MarketLatestSnapshotResponse:
    """Build a MarketLatestSnapshot for `ticker`.

    Raises:
        ValueError("chain_not_yet_ingested") — no chain rows for ticker.
        ValueError("insufficient_iv_history") — iv_history count < 30.

    The router maps both to 422.
    """
    effective_as_of = as_of if as_of is not None else datetime.now(timezone.utc)  # noqa: UP017

    # 1. Validate prerequisites.
    iv_count = await session.execute(
        text("SELECT COUNT(*) FROM iv_history WHERE ticker = :ticker;"),
        {"ticker": ticker},
    )
    iv_n = iv_count.scalar() or 0
    if int(iv_n) < _MIN_IV_ROWS:
        raise ValueError(
            f"insufficient_iv_history: ticker={ticker!r} has {int(iv_n)} rows; "
            f"need >= {_MIN_IV_ROWS}."
        )

    chain_count = await session.execute(
        text("SELECT COUNT(*) FROM option_chain_snapshots WHERE ticker = :ticker;"),
        {"ticker": ticker},
    )
    chain_n = chain_count.scalar() or 0
    if int(chain_n) < 1:
        raise ValueError(
            f"chain_not_yet_ingested: no option_chain_snapshots rows for ticker={ticker!r}."
        )

    # 2. Latest chain rows (all rows at the most recent fetched_at).
    chain_rows = await session.execute(
        text(
            """
            WITH latest AS (
                SELECT MAX(fetched_at) AS f FROM option_chain_snapshots
                WHERE ticker = :ticker
            )
            SELECT expiry, strike, kind, bid, ask, last, mark,
                   oi, volume, iv, delta, gamma, theta, vega, fetched_at
            FROM option_chain_snapshots, latest
            WHERE ticker = :ticker AND fetched_at = latest.f
            ORDER BY expiry, kind, strike;
            """
        ),
        {"ticker": ticker},
    )
    rows = chain_rows.fetchall()
    if not rows:
        raise ValueError(
            f"chain_not_yet_ingested: latest snapshot has no rows for ticker={ticker!r}."
        )
    chain_fetched_at: datetime = rows[0][14]

    # 3. Build engine OptionContract list + derive spot.
    contracts: list[OptionContract] = []
    expiries_present: set[Any] = set()
    for r in rows:
        expiry, strike, kind, bid, ask, last_, mark, oi, volume, iv, delta, gamma, theta, vega, _ = r
        expiries_present.add(expiry)
        contracts.append(
            OptionContract(
                underlying=ticker,
                expiry=expiry,
                strike=float(strike),
                option_type=OptionType(str(kind)),
                bid=float(bid) if bid is not None else None,
                ask=float(ask) if ask is not None else None,
                iv=float(iv) if iv is not None else None,
                mid=float(mark) if mark is not None else (float(last_) if last_ is not None else None),
                open_interest=int(oi or 0),
                volume=int(volume or 0),
            )
        )

    # Derive spot via highest-OI strike at the nearest expiry (V1 heuristic).
    nearest_expiry = min(expiries_present)
    spot = _derive_spot(contracts=contracts, nearest_expiry=nearest_expiry)

    # 4. Compute max pain via engine primitive (at the nearest expiry).
    try:
        max_pain_value = compute_max_pain(contracts=contracts, expiry=nearest_expiry)
    except Exception:  # noqa: BLE001 — defensive against insufficient strike coverage
        max_pain_value = None

    # 5. PCR volume + PCR OI across the nearest expiry's rows.
    nearest_contracts = [c for c in contracts if c.expiry == nearest_expiry]
    try:
        pcr_v = compute_pcr_volume(contracts=nearest_contracts)
    except Exception:  # noqa: BLE001
        pcr_v = None
    try:
        pcr_o = compute_pcr_oi(contracts=nearest_contracts)
    except Exception:  # noqa: BLE001
        pcr_o = None

    # 6. Latest iv_history + hv_history (separate queries; either may be absent).
    iv_row = await session.execute(
        text(
            """
            SELECT ts, atm_iv_30d, iv_rank, iv_percentile
            FROM iv_history WHERE ticker = :ticker
            ORDER BY ts DESC LIMIT 1;
            """
        ),
        {"ticker": ticker},
    )
    iv_latest = iv_row.first()
    atm_iv_30d: float | None = None
    iv_rank: float | None = None
    iv_percentile: float | None = None
    iv_ts: datetime | None = None
    if iv_latest is not None:
        iv_ts, _atm_iv_30d, _iv_rank, _iv_pct = iv_latest
        atm_iv_30d = float(_atm_iv_30d) if _atm_iv_30d is not None else None
        iv_rank = float(_iv_rank) if _iv_rank is not None else None
        iv_percentile = float(_iv_pct) if _iv_pct is not None else None

    hv_row = await session.execute(
        text(
            """
            SELECT ts, hv_30 FROM hv_history WHERE ticker = :ticker
            ORDER BY ts DESC LIMIT 1;
            """
        ),
        {"ticker": ticker},
    )
    hv_latest = hv_row.first()
    hv_30: float | None = None
    hv_ts: datetime | None = None
    if hv_latest is not None:
        hv_ts, _hv_30 = hv_latest
        hv_30 = float(_hv_30) if _hv_30 is not None else None

    # 7. Expected move %: engine primitive needs ATM IV + DTE.
    expected_move = None
    if atm_iv_30d is not None and spot is not None:
        dte_days = max(1, (nearest_expiry - effective_as_of.date()).days)
        try:
            expected_move = compute_expected_move_pct(
                atm_iv=atm_iv_30d, dte_days=dte_days
            )
        except Exception:  # noqa: BLE001
            expected_move = None

    # 8. Next event (ticker-scoped or global).
    event_row = await session.execute(
        text(
            """
            SELECT id, kind, scheduled_at, ticker, notes
            FROM events
            WHERE (ticker = :ticker OR ticker IS NULL)
              AND scheduled_at > :as_of
            ORDER BY scheduled_at ASC LIMIT 1;
            """
        ),
        {"ticker": ticker, "as_of": effective_as_of},
    )
    event_latest = event_row.first()
    next_event: dict[str, Any] | None = None
    if event_latest is not None:
        eid, ekind, eat, ettkr, enotes = event_latest
        next_event = {
            "id": str(eid),
            "kind": str(ekind),
            "scheduled_at": eat.isoformat() if isinstance(eat, datetime) else str(eat),
            "ticker": ettkr,
            "notes": enotes,
        }

    # 9. Staleness flags.
    freshness = _build_freshness(
        as_of=effective_as_of,
        chain_at=chain_fetched_at,
        iv_at=iv_ts,
        hv_at=hv_ts,
    )

    return MarketLatestSnapshotResponse(
        as_of=effective_as_of,
        ticker=ticker,
        spot=Decimal(str(spot)) if spot is not None else Decimal("0"),
        iv_rank=iv_rank,
        iv_percentile=iv_percentile,
        hv_30=hv_30,
        expected_move_pct=expected_move,
        max_pain=Decimal(str(max_pain_value)) if max_pain_value is not None else None,
        pcr_volume=pcr_v,
        pcr_oi=pcr_o,
        next_event=next_event,
        data_freshness=freshness,
    )


# ----------------------------------------------------------------------
# Internals
# ----------------------------------------------------------------------


def _derive_spot(
    *, contracts: list[OptionContract], nearest_expiry: Any
) -> float | None:
    """V1 spot heuristic: strike with highest combined OI at the nearest expiry.

    Returns None when no contracts have OI > 0 (extremely unlikely in
    practice; only happens for synthetic or empty chains).
    """
    by_strike: dict[float, int] = {}
    for c in contracts:
        if c.expiry != nearest_expiry:
            continue
        by_strike[c.strike] = by_strike.get(c.strike, 0) + (c.open_interest or 0)
    if not by_strike:
        return None
    # Return the strike with the maximum aggregated OI. On tie, prefer
    # the strike closest to the median (more ATM-like).
    max_oi = max(by_strike.values())
    if max_oi == 0:
        # Fall back to the median strike.
        sorted_strikes = sorted(by_strike.keys())
        return sorted_strikes[len(sorted_strikes) // 2]
    candidates = [k for k, v in by_strike.items() if v == max_oi]
    if len(candidates) == 1:
        return candidates[0]
    sorted_strikes = sorted(by_strike.keys())
    median = sorted_strikes[len(sorted_strikes) // 2]
    return min(candidates, key=lambda s: abs(s - median))


def _build_freshness(
    *,
    as_of: datetime,
    chain_at: datetime,
    iv_at: datetime | None,
    hv_at: datetime | None,
) -> DataFreshness:
    chain_age = int((as_of - chain_at).total_seconds()) if chain_at else None
    iv_age = int((as_of - iv_at).total_seconds()) if iv_at else None
    hv_age = int((as_of - hv_at).total_seconds()) if hv_at else None

    stale_tags: list[str] = []
    if chain_age is not None and chain_age > _CHAIN_STALE_SECONDS:
        stale_tags.append("stale_chain")
    if iv_age is not None and iv_age > _IV_STALE_SECONDS:
        stale_tags.append("stale_iv")
    if hv_age is not None and hv_age > _HV_STALE_SECONDS:
        stale_tags.append("stale_hv")

    return DataFreshness(
        chain_age_seconds=max(0, chain_age) if chain_age is not None else None,
        iv_age_seconds=max(0, iv_age) if iv_age is not None else None,
        hv_age_seconds=max(0, hv_age) if hv_age is not None else None,
        any_stale=bool(stale_tags),
        stale_tags=stale_tags,
    )
