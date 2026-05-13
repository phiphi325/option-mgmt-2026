"""Collar builder service — M1.16a.

Thin I/O layer between the API router and `engine.collar_builder.build()`.
The engine call is pure (no DB, no side effects); this service owns all DB
reads:

  - `option_chain_snapshots`  → ChainSnapshot + spot
  - `positions`               → underlying_qty (§22.11 H5 — never from body)
  - `iv_history` + related    → MarketStateResult (via classify())
  - `option_chain_snapshots`  → FlowScore (via flow_score.compute())
  - `users.strategy_profile`  → UserStrategyProfile

Per plan v1.2 §7, §9.10 (Collar Builder), §22.11 H5, M1.16a dev spec.
"""

from __future__ import annotations

from engine.collar_builder import CollarStructure as EngineCollarStructure
from engine.collar_builder import build
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.engine import CollarBuilderRequest, CollarStructureResponse
from app.services.inputs_hydration_service import (  # noqa: PLC2701
    _hydrate_chain_snapshot,
    _hydrate_flow_score,
    _hydrate_market_state,
    _hydrate_profile,
)

# Phase 1: MSFT-only guard.  Matches `SUPPORTED_TICKERS` in market_service.
_SUPPORTED_TICKERS: frozenset[str] = frozenset({"MSFT"})

# Mirrors `_MIN_IV_ROWS` in inputs_hydration_service — same 30-row gate.
_MIN_IV_ROWS = 30


async def run_collar_builder(
    *,
    session: AsyncSession,
    user_id: str,
    request: CollarBuilderRequest,
) -> list[CollarStructureResponse]:
    """Build ranked collar candidates for up to three intents.

    Implements the §22.11 H5 contract: `underlying_qty` is always resolved
    from the DB, never from the request body.

    Args:
        session:   Async SQLAlchemy session (from `app.deps.get_session`).
        user_id:   Authenticated user UUID (string).
        request:   Validated `CollarBuilderRequest` from the HTTP layer.

    Returns:
        A list of `CollarStructureResponse` objects, intent-ordered
        (ZERO_COST → INCOME → DEFENSIVE). Infeasible intents are absent
        from the list (the engine skips intents with no feasible structure
        rather than inserting nulls).

    Raises:
        ValueError: Propagated from guards or engine; the router maps all
            shapes to HTTP 422:

              "unsupported_ticker"        — ticker not in SUPPORTED_TICKERS
              "missing_chain"             — no option_chain_snapshots rows
              "insufficient_iv_history"   — iv_history < 30 rows
              "insufficient_shares"       — underlying_qty < 100 shares
    """
    ticker = request.ticker

    # ── 1. Ticker guard (Phase 1: MSFT only) ──────────────────────────────
    if ticker not in _SUPPORTED_TICKERS:
        raise ValueError(
            f"unsupported_ticker: {ticker!r} is not supported in Phase 1 "
            f"(supported: {sorted(_SUPPORTED_TICKERS)})"
        )

    # ── 2. Load chain snapshot (raises ValueError("missing_chain") if absent) ─
    chain_snapshot, contracts, _ = await _hydrate_chain_snapshot(
        session=session, ticker=ticker
    )
    spot = chain_snapshot.spot  # derived spot already set by the helper

    # ── 3. IV history gate (mirrors hydrate_engine_inputs §22.12) ─────────
    iv_count_row = await session.execute(
        text("SELECT COUNT(*) FROM iv_history WHERE ticker = :ticker;"),
        {"ticker": ticker},
    )
    iv_n = int(iv_count_row.scalar() or 0)
    if iv_n < _MIN_IV_ROWS:
        raise ValueError(
            f"insufficient_iv_history: ticker={ticker!r} has {iv_n} rows; "
            f"need >= {_MIN_IV_ROWS}."
        )

    # ── 4. Underlying qty from DB (§22.11 H5 — never from request body) ───
    qty_row = await session.execute(
        text(
            "SELECT COALESCE(SUM(qty), 0) FROM positions "
            "WHERE user_id = :user_id AND ticker = :ticker;"
        ),
        {"user_id": user_id, "ticker": ticker},
    )
    underlying_qty = int(qty_row.scalar() or 0)
    if underlying_qty < 100:
        raise ValueError(
            f"insufficient_shares: {underlying_qty} {ticker} shares on record; "
            "need >= 100 (1 standard contract) to build a collar."
        )

    # ── 5. User profile (returns defaults when no row; never raises) ──────
    from datetime import datetime, timezone

    as_of = datetime.now(timezone.utc)  # noqa: UP017
    profile = await _hydrate_profile(session=session, user_id=user_id)

    # ── 6. Market state + flow score (engine prerequisites) ───────────────
    market_state = await _hydrate_market_state(
        session=session,
        ticker=ticker,
        contracts=contracts,
        spot=spot,
        as_of=as_of,
    )
    flow_score = _hydrate_flow_score(
        chain_snapshot=chain_snapshot, spot=spot, as_of=as_of
    )

    # ── 7. Engine call — pure function, no I/O ────────────────────────────
    structures: list[EngineCollarStructure] = build(
        spot=spot,
        underlying_qty=underlying_qty,
        chain=chain_snapshot,
        profile=profile,
        market_state=market_state,
        flow_score=flow_score,
        intents=list(request.intents),
        horizon_days=request.horizon_days,
        coverage_ratio=request.coverage_ratio,
    )

    # ── 8. Project engine dataclasses → API response models ───────────────
    return [CollarStructureResponse.from_engine(s) for s in structures]
