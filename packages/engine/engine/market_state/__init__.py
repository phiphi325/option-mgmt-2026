"""Market State Engine — primitives + `classify()` entry point.

Per plan v1.2 §9.1 (Market State Engine inputs) and §17 M1.1–M1.4.

This sub-package builds the Market State Engine incrementally:

  M1.1 (shipped)
    iv_rank             range-based IV rank in [0, 1]
    iv_percentile       count-based IV percentile in [0, 1]
    compute_hv          annualized historical volatility (sample stddev)

  M1.2 (shipped)
    compute_max_pain    CBOE-style max pain strike (per §22.9)
    expected_move       one-σ expected dollar move at DTE
    expected_move_pct   same, as fraction of spot
    pcr_volume          Σ put volume / Σ call volume
    pcr_oi              Σ put OI / Σ call OI

  M1.3 (shipped)
    compute_trend_strength  Wilder ADX, normalized to [0, 1] (per §22.5)
    wilder_adx              raw ADX value (helper, exposed for diagnostics)
    compute_breakout_signal composite [0, 1] signal (per §22.5)

  M1.4 (this milestone)
    classify()              full Market State Engine + 6-regime selector
    MarketStateResult       result dataclass with regime, score, tags

Pure functions. No I/O. No DB. No network. Inputs are simple Python
values + frozen `OptionContract` records; outputs are floats or frozen
result dataclasses. Edge cases (insufficient history, degenerate ranges,
non-positive prices, missing expiries) raise `ValueError` — callers
absorb staleness per plan §22.12 IV-history validation, which gates
`POST /engine/daily-plan` at HTTP 422.

The `compute_trend_strength` non-raising path on insufficient history
(returns 0.5) is the deliberate exception (per §22.5) — `classify()`
keeps running rather than bailing when ADX history is thin.
"""

from __future__ import annotations

from engine.market_state.breakout import compute_breakout_signal
from engine.market_state.classify import MarketStateResult, classify
from engine.market_state.expected_move import expected_move, expected_move_pct
from engine.market_state.hv import compute_hv
from engine.market_state.iv import iv_percentile, iv_rank
from engine.market_state.max_pain import compute_max_pain
from engine.market_state.pcr import pcr_oi, pcr_volume
from engine.market_state.trend_strength import compute_trend_strength, wilder_adx

__all__ = [
    # M1.1
    "compute_hv",
    "iv_percentile",
    "iv_rank",
    # M1.2
    "compute_max_pain",
    "expected_move",
    "expected_move_pct",
    "pcr_oi",
    "pcr_volume",
    # M1.3
    "compute_breakout_signal",
    "compute_trend_strength",
    "wilder_adx",
    # M1.4
    "MarketStateResult",
    "classify",
]
