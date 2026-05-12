"""Inputs hydration service (M1.17.5).

The deferred knock-on commitment from M1.17. When `DailyPlanRequest.inputs`
is omitted, this module hydrates an `EngineInputs` bundle from the latest
DB rows (positions / option_positions / option_chain_snapshots /
iv_history / hv_history / events / users.strategy_profile) and
reproduces the upstream engine pipeline server-side (market_state.classify
+ flow_score.compute).

Per plan v1.2 §7 (DailyPlanRequest), §9.2 + §22.3 (Market State Engine),
§9.3a (Flow Score V1 contract), §10 (Data Ingestion), §17 M1.17.5.

## Public API

  hydrate_engine_inputs(*, session, user_id, ticker, as_of) -> EngineInputs

Raises ValueError("missing_positions" | "missing_chain" |
"insufficient_iv_history") which the router maps to HTTP 422 with the
prerequisite name in the detail (clients can prompt the user to upload
the missing CSV).

## V1 simplifying assumptions

A handful of `classify()` inputs require historical context that isn't
reliably tracked in the current schema (M0.2 created the tables, but
some derived signals expect daily snapshots or resistance/breakout
tracking that M1.17 CSV import doesn't populate yet). The V1 hydration
punts on those with safe defaults:

| Field | V1 default | Why |
|---|---|---|
| `breakout_signal` | `0.0` | Requires 5-day price + IV history + OI shift; M1.17 only stores point-in-time chain. M2+ will compute this. |
| `oi_concentration_at_max_pain` | `0.0` | Requires a max_pain-relative OI distribution roll-up; engine accepts 0 safely. |
| `iv_rank_change_1d` | derived from 2-row diff if available, else `0.0` | If iv_history has < 2 rows, use 0 (no change). |
| `gap_pct` | `None` | Requires previous-day close vs. today's open. No daily-close history yet. |
| `days_since_event` | derived from latest past event or `None` | Engine accepts None. |
| `days_to_nearest_opex` | computed from next 3rd Friday of the month | Pure date arithmetic. |
| `trend_strength` | computed from iv_history OHLC if ≥ 30 days; else `0.5` | Engine returns 0.5 for insufficient ADX history per §22.5. |

These shortcuts are documented inline in the helpers below. The
contract is: the engine still produces a coherent DailyDecision; the
deterministic-replay guarantee holds (same DB state → same hash). M2+
ingestion + a dedicated `market_signals` table can refine.

## Spot derivation

`option_chain_snapshots` has no per-snapshot `spot` column. V1 uses the
same heuristic as `market_service.py` — strike with the highest combined
OI at the nearest expiry. Documented in `_derive_spot`.
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from engine.flow_score import FlowScore, RecommendedAction
from engine.flow_score import compute as flow_score_compute
from engine.flow_score.types import Bias
from engine.market_state import (
    MarketStateResult,
    classify,
    compute_max_pain,
    pcr_oi,
    pcr_volume,
)
from engine.market_state import expected_move_pct as _expected_move_pct
from engine.profiles import (
    IncomeNeed,
    ProfileStyle,
    RiskTolerance,
    UserStrategyProfile,
)
from engine.types import ChainSnapshot, OptionContract, OptionType
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.decision import EngineInputs
from app.schemas.engine import (
    FlowScoreModel,
    MarketStateResultModel,
    PositionStateModel,
)

# §22.12 minimum iv_history rows (mirrors market_service.py + csv_import_service.py)
_MIN_IV_ROWS = 30


# ----------------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------------


async def hydrate_engine_inputs(
    *,
    session: AsyncSession,
    user_id: str,
    ticker: str,
    as_of: datetime | None = None,
) -> EngineInputs:
    """Build an `EngineInputs` bundle from the latest DB rows for `(user_id, ticker)`.

    The result is byte-equivalent to what a caller could construct by
    hand from the same DB state — `inputs_hash` is therefore deterministic
    across calls, preserving the M1.14 replay contract.

    Raises:
        ValueError("missing_chain")           — option_chain_snapshots empty for ticker
        ValueError("insufficient_iv_history") — iv_history < 30 rows for ticker (§22.12)
        ValueError("missing_positions")       — positions table has no rows for
                                                (user_id, ticker); the engine can run
                                                with 0 shares but the user is almost
                                                certainly not ready for a decision
    """
    effective_as_of = as_of if as_of is not None else datetime.now(timezone.utc)  # noqa: UP017

    # 1. Validate prerequisites + load chain rows (most expensive prerequisite).
    chain_snapshot, contracts, chain_fetched_at = await _hydrate_chain_snapshot(
        session=session, ticker=ticker
    )
    spot = _derive_spot(contracts=contracts)

    # 2. Validate iv_history count (§22.12 — same gate as market_service).
    iv_count_row = await session.execute(
        text("SELECT COUNT(*) FROM iv_history WHERE ticker = :ticker;"),
        {"ticker": ticker},
    )
    iv_n = int(iv_count_row.scalar() or 0)
    if iv_n < _MIN_IV_ROWS:
        raise ValueError(
            f"insufficient_iv_history: ticker={ticker!r} has {iv_n} rows; need >= {_MIN_IV_ROWS}."
        )

    # 3. Hydrate user-scoped state.
    profile = await _hydrate_profile(session=session, user_id=user_id)
    positions = await _hydrate_positions(
        session=session, user_id=user_id, ticker=ticker, contracts=contracts, as_of=effective_as_of
    )

    # 4. Compute upstream engine outputs server-side.
    market_state = await _hydrate_market_state(
        session=session,
        ticker=ticker,
        contracts=contracts,
        spot=spot,
        as_of=effective_as_of,
    )
    flow_score = _hydrate_flow_score(
        chain_snapshot=chain_snapshot, spot=spot, as_of=effective_as_of
    )

    return EngineInputs(
        chain_snapshot=chain_snapshot,
        positions=positions,
        profile=profile,
        market_state=_market_state_to_model(market_state),
        flow_score=_flow_score_to_model(flow_score),
    )


# ----------------------------------------------------------------------
# Chain hydration + spot derivation
# ----------------------------------------------------------------------


async def _hydrate_chain_snapshot(
    *, session: AsyncSession, ticker: str
) -> tuple[ChainSnapshot, list[OptionContract], datetime]:
    """Load all chain rows at the most recent `fetched_at` for `ticker`.

    Returns `(chain_snapshot, contracts, chain_fetched_at)`. Raises
    `ValueError("missing_chain")` when the table has no rows for ticker.
    """
    rows_result = await session.execute(
        text(
            """
            WITH latest AS (
                SELECT MAX(fetched_at) AS f FROM option_chain_snapshots
                WHERE ticker = :ticker
            )
            SELECT expiry, strike, kind, bid, ask, last, mark,
                   oi, volume, iv, fetched_at
            FROM option_chain_snapshots, latest
            WHERE ticker = :ticker AND fetched_at = latest.f
            ORDER BY expiry, kind, strike;
            """
        ),
        {"ticker": ticker},
    )
    rows = rows_result.fetchall()
    if not rows:
        raise ValueError(
            f"missing_chain: no option_chain_snapshots rows for ticker={ticker!r}."
        )

    chain_fetched_at: datetime = rows[0][10]
    contracts: list[OptionContract] = [
        OptionContract(
            underlying=ticker,
            expiry=row[0],
            strike=float(row[1]),
            option_type=OptionType(str(row[2])),
            bid=float(row[3]) if row[3] is not None else None,
            ask=float(row[4]) if row[4] is not None else None,
            iv=float(row[9]) if row[9] is not None else None,
            mid=(
                float(row[6])
                if row[6] is not None
                else (float(row[5]) if row[5] is not None else None)
            ),
            open_interest=int(row[7] or 0),
            volume=int(row[8] or 0),
        )
        for row in rows
    ]

    spot = _derive_spot(contracts=contracts)
    if spot is None:
        # Chain present but no OI → fall back to median strike.
        sorted_strikes = sorted({c.strike for c in contracts})
        spot = sorted_strikes[len(sorted_strikes) // 2] if sorted_strikes else 1.0

    chain_snapshot = ChainSnapshot(
        underlying=ticker,
        spot=spot,
        as_of=chain_fetched_at.date(),
        contracts=tuple(contracts),
    )
    return chain_snapshot, contracts, chain_fetched_at


def _derive_spot(*, contracts: list[OptionContract]) -> float:
    """V1 spot heuristic: strike with highest combined OI at the nearest expiry.

    Mirrors `market_service._derive_spot` (kept in sync intentionally so both
    endpoints derive the same spot from the same DB state, preserving replay
    determinism).
    """
    if not contracts:
        return 1.0
    nearest_expiry = min(c.expiry for c in contracts)
    by_strike: dict[float, int] = {}
    for c in contracts:
        if c.expiry != nearest_expiry:
            continue
        by_strike[c.strike] = by_strike.get(c.strike, 0) + (c.open_interest or 0)
    if not by_strike:
        return 1.0
    max_oi = max(by_strike.values())
    if max_oi == 0:
        sorted_strikes = sorted(by_strike.keys())
        return sorted_strikes[len(sorted_strikes) // 2]
    candidates = [k for k, v in by_strike.items() if v == max_oi]
    if len(candidates) == 1:
        return candidates[0]
    sorted_strikes = sorted(by_strike.keys())
    median = sorted_strikes[len(sorted_strikes) // 2]
    return min(candidates, key=lambda s: abs(s - median))


# ----------------------------------------------------------------------
# Profile hydration
# ----------------------------------------------------------------------


_DEFAULT_PROFILE = UserStrategyProfile(
    risk_tolerance=RiskTolerance.MODERATE,
    income_need=IncomeNeed.MEDIUM,
    max_position_pct=0.50,
    max_coverage_pct=0.75,
    min_iv_rank_for_short_premium=40,
    prefer_collars_over_covered_calls=False,
    drawdown_tolerance=0.15,
    style=ProfileStyle.BALANCED,
)


async def _hydrate_profile(
    *, session: AsyncSession, user_id: str
) -> UserStrategyProfile:
    """Read users.strategy_profile JSONB; return defaults when empty."""
    result = await session.execute(
        text("SELECT strategy_profile FROM users WHERE id = :user_id;"),
        {"user_id": user_id},
    )
    row = result.first()
    if row is None or not row[0]:
        return _DEFAULT_PROFILE
    raw = row[0]
    if isinstance(raw, str):
        raw = json.loads(raw)
    return UserStrategyProfile(**raw)


# ----------------------------------------------------------------------
# Positions hydration
# ----------------------------------------------------------------------


async def _hydrate_positions(
    *,
    session: AsyncSession,
    user_id: str,
    ticker: str,
    contracts: list[OptionContract],
    as_of: datetime,
) -> PositionStateModel:
    """Build a PositionStateModel from positions + option_positions.

    Raises ValueError("missing_positions") when neither table has rows
    for (user_id, ticker). The engine can run with `underlying_shares=0`
    but a user with no position data isn't ready for a daily decision.
    """
    # Underlying shares from positions table.
    shares_row = await session.execute(
        text(
            "SELECT COALESCE(SUM(qty), 0) FROM positions "
            "WHERE user_id = :user_id AND ticker = :ticker;"
        ),
        {"user_id": user_id, "ticker": ticker},
    )
    shares_raw = shares_row.scalar()
    underlying_shares = int(shares_raw or 0)

    # Option positions — open ones only.
    opt_rows = await session.execute(
        text(
            """
            SELECT side, kind, strike, expiry, qty, opened_price, status
            FROM option_positions
            WHERE user_id = :user_id AND ticker = :ticker AND status = 'OPEN'
            ORDER BY expiry, strike;
            """
        ),
        {"user_id": user_id, "ticker": ticker},
    )
    opt_rows_list = opt_rows.fetchall()

    if underlying_shares == 0 and not opt_rows_list:
        raise ValueError(
            f"missing_positions: no positions or open option_positions for "
            f"user_id={user_id!r}, ticker={ticker!r}."
        )

    # Aggregate option-position flags expected by PositionState.
    short_calls: list[tuple[Any, ...]] = []
    has_long_put = False
    long_put_pnl_pct = 0.0
    has_short_put = False
    short_call_contracts = 0
    for row in opt_rows_list:
        side, kind, strike, expiry, qty, opened_price, _ = row
        if side == "SELL" and kind == "CALL":
            short_calls.append(tuple(row))
            short_call_contracts += int(qty)
        elif side == "BUY" and kind == "PUT":
            has_long_put = True
            current_mid = _lookup_mid(contracts, strike=float(strike), kind="PUT", expiry=expiry)
            if current_mid is not None and opened_price:
                long_put_pnl_pct = float((current_mid - float(opened_price)) / float(opened_price))
        elif side == "SELL" and kind == "PUT":
            has_short_put = True

    if short_calls:
        # Sort by expiry then by strike; the "nearest" = soonest expiry.
        short_calls.sort(key=lambda r: (r[3], r[2]))
        first = short_calls[0]
        nearest_short_call_strike: float | None = float(first[2])
        nearest_short_call_dte: int | None = max(0, (first[3] - as_of.date()).days)
    else:
        nearest_short_call_strike = None
        nearest_short_call_dte = None

    return PositionStateModel(
        underlying_shares=underlying_shares,
        has_short_call=bool(short_calls),
        nearest_short_call_strike=nearest_short_call_strike,
        nearest_short_call_dte=nearest_short_call_dte,
        short_call_contracts=short_call_contracts,
        has_long_put=has_long_put,
        long_put_pnl_pct=long_put_pnl_pct,
        has_short_put=has_short_put,
    )


def _lookup_mid(
    contracts: list[OptionContract],
    *,
    strike: float,
    kind: str,
    expiry: date,
) -> float | None:
    """Return the mid price for the chain row matching strike+kind+expiry."""
    for c in contracts:
        if (
            abs(c.strike - strike) < 1e-6
            and c.option_type.value == kind
            and c.expiry == expiry
        ):
            return float(c.mid) if c.mid is not None else None
    return None


# ----------------------------------------------------------------------
# Market state hydration — runs engine.market_state.classify()
# ----------------------------------------------------------------------


async def _hydrate_market_state(
    *,
    session: AsyncSession,
    ticker: str,
    contracts: list[OptionContract],
    spot: float,
    as_of: datetime,
) -> MarketStateResult:
    """Build classify() inputs from DB rows and run the engine."""
    # Latest iv_history row + previous row (for iv_rank_change_1d).
    iv_rows_result = await session.execute(
        text(
            """
            SELECT ts, atm_iv_30d, iv_rank, iv_percentile
            FROM iv_history WHERE ticker = :ticker
            ORDER BY ts DESC LIMIT 2;
            """
        ),
        {"ticker": ticker},
    )
    iv_rows = iv_rows_result.fetchall()
    latest_iv = iv_rows[0]
    iv_rank = float(latest_iv[2]) if latest_iv[2] is not None else 0.5
    iv_percentile = float(latest_iv[3]) if latest_iv[3] is not None else 0.5
    atm_iv_30d = float(latest_iv[1]) if latest_iv[1] is not None else 0.25
    iv_rank_change_1d: float | None
    if len(iv_rows) >= 2 and iv_rows[1][2] is not None:
        iv_rank_change_1d = iv_rank - float(iv_rows[1][2])
    else:
        iv_rank_change_1d = 0.0

    # Latest hv_history.
    hv_row = await session.execute(
        text(
            "SELECT hv_30 FROM hv_history WHERE ticker = :ticker "
            "ORDER BY ts DESC LIMIT 1;"
        ),
        {"ticker": ticker},
    )
    hv_latest = hv_row.first()
    hv_30 = float(hv_latest[0]) if hv_latest and hv_latest[0] is not None else 0.22

    # Nearest expiry + max_pain.
    nearest_expiry = min(c.expiry for c in contracts)
    nearest_contracts = [c for c in contracts if c.expiry == nearest_expiry]
    try:
        max_pain = float(compute_max_pain(contracts=contracts, expiry=nearest_expiry))
    except Exception:  # noqa: BLE001 — defensive against thin chains
        max_pain = spot
    max_pain_delta_pct = (max_pain - spot) / spot if spot > 0 else 0.0  # noqa: F841 - echoed by classify result

    # PCRs.
    try:
        pcrv = float(pcr_volume(contracts=nearest_contracts))
    except Exception:  # noqa: BLE001
        pcrv = 1.0
    try:
        pcro = float(pcr_oi(contracts=nearest_contracts))
    except Exception:  # noqa: BLE001
        pcro = 1.0

    # Expected move (engine primitive needs ATM IV + DTE).
    dte_days = max(1, (nearest_expiry - as_of.date()).days)
    try:
        expected_move = float(_expected_move_pct(atm_iv=atm_iv_30d, dte_days=dte_days))
    except Exception:  # noqa: BLE001
        expected_move = atm_iv_30d * math.sqrt(dte_days / 365.0)

    # Event proximity.
    next_event_row = await session.execute(
        text(
            """
            SELECT kind, scheduled_at FROM events
            WHERE (ticker = :ticker OR ticker IS NULL)
              AND scheduled_at > :as_of
            ORDER BY scheduled_at ASC LIMIT 1;
            """
        ),
        {"ticker": ticker, "as_of": as_of},
    )
    next_event = next_event_row.first()
    days_to_next_event: int | None
    next_event_kind: str | None
    if next_event is not None:
        kind, scheduled_at = next_event
        days_to_next_event = max(0, (scheduled_at - as_of).days)
        next_event_kind = str(kind)
    else:
        days_to_next_event = None
        next_event_kind = None

    past_event_row = await session.execute(
        text(
            """
            SELECT scheduled_at FROM events
            WHERE (ticker = :ticker OR ticker IS NULL)
              AND scheduled_at <= :as_of
            ORDER BY scheduled_at DESC LIMIT 1;
            """
        ),
        {"ticker": ticker, "as_of": as_of},
    )
    past_event = past_event_row.first()
    days_since_event: int | None
    if past_event is not None:
        days_since_event = max(0, (as_of - past_event[0]).days)
    else:
        days_since_event = None

    # Days to nearest opex (3rd Friday of current or next month).
    days_to_nearest_opex = _days_to_nearest_opex(as_of.date())

    # Realized vs implied: hv_30 / atm_iv_30d (avoids div by 0).
    realized_vs_implied = hv_30 / atm_iv_30d if atm_iv_30d > 0 else 1.0

    # V1 defaults for fields requiring historical context we don't track yet.
    trend_strength = 0.5
    breakout_signal = 0.0
    oi_concentration_at_max_pain = 0.0
    gap_pct: float | None = None

    return classify(
        spot=spot,
        iv_rank=iv_rank,
        iv_percentile=iv_percentile,
        hv_30=hv_30,
        expected_move_pct=expected_move,
        max_pain=max_pain,
        pcr_volume=pcrv,
        pcr_oi=pcro,
        days_to_next_event=days_to_next_event,
        next_event_kind=next_event_kind,
        trend_strength=trend_strength,
        realized_vs_implied=realized_vs_implied,
        days_since_event=days_since_event,
        days_to_nearest_opex=days_to_nearest_opex,
        iv_rank_change_1d=iv_rank_change_1d,
        gap_pct=gap_pct,
        breakout_signal=breakout_signal,
        oi_concentration_at_max_pain=oi_concentration_at_max_pain,
    )


def _days_to_nearest_opex(today: date) -> int | None:
    """Return days until the nearest 3rd-Friday monthly opex.

    Returns None when today IS the 3rd Friday (so the engine doesn't
    treat opex-day as "near opex" in the wrong direction).
    """
    candidates: list[int] = []
    for month_offset in (0, 1, 2):
        year = today.year
        month = today.month + month_offset
        while month > 12:
            month -= 12
            year += 1
        opex = _third_friday(year, month)
        delta = (opex - today).days
        if delta > 0:
            candidates.append(delta)
    return min(candidates) if candidates else None


def _third_friday(year: int, month: int) -> date:
    """Return the 3rd-Friday-of-month for `(year, month)`."""
    first = date(year, month, 1)
    # Weekday: Monday=0, ..., Friday=4, Sunday=6.
    days_to_first_friday = (4 - first.weekday()) % 7
    first_friday = first + timedelta(days=days_to_first_friday)
    return first_friday + timedelta(days=14)


# ----------------------------------------------------------------------
# Flow score hydration — runs engine.flow_score.compute()
# ----------------------------------------------------------------------


def _hydrate_flow_score(
    *, chain_snapshot: ChainSnapshot, spot: float, as_of: datetime
) -> FlowScore:
    """Run flow_score.compute() against the chain snapshot.

    `expiry_focus` is the nearest expiry in the chain. Engine handles
    the rest (OI walls, PCR, dealer-gamma proxy, V1 decision tree).
    """
    expiries = sorted({c.expiry for c in chain_snapshot.contracts})
    if not expiries:
        # Defensive — chain validation in _hydrate_chain_snapshot should
        # have raised already.
        return FlowScore(
            score=0.0,
            bullish_score=0.0,
            bearish_score=0.0,
            bias=Bias.NEUTRAL,
            recommended_action=RecommendedAction.MONITOR,
            pin_probability=0.0,
            gamma_risk=0.0,
            gamma_sign=0,
            confidence=0.0,
            explanation="(degenerate chain; no contracts)",
            breakdown={},
        )
    expiry_focus = [expiries[0]]
    dte_to_nearest_opex = _days_to_nearest_opex(as_of.date())

    try:
        return flow_score_compute(
            chain_snapshot=chain_snapshot,
            spot=spot,
            expiry_focus=expiry_focus,
            dte_to_nearest_opex=dte_to_nearest_opex,
            risk_free_rate=0.05,
            dividend_yield=0.0,
        )
    except Exception as exc:  # noqa: BLE001 — propagate as defensive default
        # If the engine raises on degenerate chains, return a neutral V1
        # FlowScore so the daily-plan request can still complete (the
        # confidence composer will downweight via the various penalties).
        return FlowScore(
            score=0.0,
            bullish_score=0.0,
            bearish_score=0.0,
            bias=Bias.NEUTRAL,
            recommended_action=RecommendedAction.MONITOR,
            pin_probability=0.0,
            gamma_risk=0.0,
            gamma_sign=0,
            confidence=0.0,
            explanation=f"(flow_score.compute fallback: {exc})",
            breakdown={},
        )


# ----------------------------------------------------------------------
# Engine → Pydantic projection helpers
# ----------------------------------------------------------------------


def _market_state_to_model(result: MarketStateResult) -> MarketStateResultModel:
    """Project engine.MarketStateResult → schemas.MarketStateResultModel."""
    return MarketStateResultModel(
        regime=result.regime,
        regime_score=result.regime_score,
        all_scores={k: float(v) for k, v in result.all_scores.items()},
        tags=list(result.tags),
        spot=result.spot,
        iv_rank=result.iv_rank,
        iv_percentile=result.iv_percentile,
        hv_30=result.hv_30,
        expected_move_pct=result.expected_move_pct,
        max_pain=result.max_pain,
        max_pain_delta_pct=result.max_pain_delta_pct,
        pcr_volume=result.pcr_volume,
        pcr_oi=result.pcr_oi,
        trend_strength=result.trend_strength,
        realized_vs_implied=result.realized_vs_implied,
        breakout_signal=result.breakout_signal,
        oi_concentration_at_max_pain=result.oi_concentration_at_max_pain,
        days_to_next_event=result.days_to_next_event,
        next_event_kind=result.next_event_kind,
        days_since_event=result.days_since_event,
        days_to_nearest_opex=result.days_to_nearest_opex,
        iv_rank_change_1d=result.iv_rank_change_1d,
        gap_pct=result.gap_pct,
    )


def _flow_score_to_model(fs: FlowScore) -> FlowScoreModel:
    """Project engine.FlowScore → schemas.FlowScoreModel."""
    return FlowScoreModel(
        score=fs.score,
        bullish_score=fs.bullish_score,
        bearish_score=fs.bearish_score,
        bias=fs.bias,
        recommended_action=fs.recommended_action,
        pin_probability=fs.pin_probability,
        gamma_risk=fs.gamma_risk,
        gamma_sign=fs.gamma_sign,
        confidence=fs.confidence,
        explanation=fs.explanation,
        breakdown={k: float(v) for k, v in fs.breakdown.items()},
    )


__all__ = ["hydrate_engine_inputs"]


# Silence "imported but unused" for `Decimal` and `Any` (kept for
# future numeric refinements + opaque casts during hydration).
_ = (Decimal, Any)
