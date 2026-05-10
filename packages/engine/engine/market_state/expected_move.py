"""Expected-move primitive.

Per plan v1.2 §9.1 (Market State Engine inputs).

Expected move is the **one-standard-deviation expected price move** over a
DTE horizon, derived from ATM IV under a lognormal-returns assumption:

  expected_move      = spot * atm_iv * sqrt(dte / 252)         (dollars)
  expected_move_pct  = atm_iv * sqrt(dte / 252)                (fraction of spot)

Annualization uses 252 trading days per year — the same constant
`hv.TRADING_DAYS_PER_YEAR` uses, registered as a single source of truth
(plan v1.2 §9.1 + §22.5).

This is a *first-order* expected-move estimator. It assumes:
  - Returns are approximately lognormal over the DTE window.
  - ATM IV is a reasonable proxy for the diffusion vol over that window.
  - No drift adjustment (the move is symmetric around spot).

For event-windows (earnings, FOMC), the lognormal assumption breaks down —
real expected moves are bimodal (gap up vs. gap down). The Market State
Engine's M1.4 `classify()` uses this scalar as one input among many, with
event_score and dte-to-event modifiers; consumers should not treat it as
a probability statement.

Pure function (per ADR-0005). No I/O. Edge cases (negative spot, IV, or
DTE) raise `ValueError`.
"""

from __future__ import annotations

import math

from engine.market_state.hv import TRADING_DAYS_PER_YEAR


def expected_move(*, spot: float, atm_iv: float, dte_days: int) -> float:
    """One-standard-deviation expected price move in dollars.

    Args:
        spot: Underlying price (must be > 0).
        atm_iv: At-the-money implied volatility, decimal form (0.30 = 30%).
                Must be >= 0; common values are 0.10..1.00.
        dte_days: Days to expiration. Must be >= 0.

    Returns:
        Expected dollar move at one standard deviation. Returns 0.0 when
        dte_days is 0 (no time, no move).

    Raises:
        ValueError: spot <= 0, atm_iv < 0, or dte_days < 0.
    """
    if spot <= 0:
        raise ValueError(f"expected_move: spot must be > 0; got {spot}")
    if atm_iv < 0:
        raise ValueError(f"expected_move: atm_iv must be >= 0; got {atm_iv}")
    if dte_days < 0:
        raise ValueError(f"expected_move: dte_days must be >= 0; got {dte_days}")
    return spot * atm_iv * math.sqrt(dte_days / TRADING_DAYS_PER_YEAR)


def expected_move_pct(*, atm_iv: float, dte_days: int) -> float:
    """One-standard-deviation expected price move as a fraction of spot.

    Same formula as `expected_move` without the `spot` factor, useful when
    callers want the percent move directly (UI labels, ratio comparisons).

    Args:
        atm_iv: At-the-money implied volatility, decimal form. Must be >= 0.
        dte_days: Days to expiration. Must be >= 0.

    Returns:
        Expected fractional move (0.04 = 4%). Returns 0.0 when dte_days is 0.

    Raises:
        ValueError: atm_iv < 0 or dte_days < 0.
    """
    if atm_iv < 0:
        raise ValueError(f"expected_move_pct: atm_iv must be >= 0; got {atm_iv}")
    if dte_days < 0:
        raise ValueError(f"expected_move_pct: dte_days must be >= 0; got {dte_days}")
    return atm_iv * math.sqrt(dte_days / TRADING_DAYS_PER_YEAR)
