"""Market State scoring primitives.

Per plan v1.2 §9.1 (Market State Engine inputs) and §17 M1.1–M1.4.

This sub-package provides the **scoring primitives** consumed by the full
Market State Engine (M1.4 `classify()`). Built incrementally:

  M1.1 (shipped)
    iv_rank             range-based IV rank in [0, 1]
    iv_percentile       count-based IV percentile in [0, 1]
    compute_hv          annualized historical volatility (sample stddev)

  M1.2 (this milestone)
    compute_max_pain    CBOE-style max pain strike (per §22.9)
    expected_move       one-σ expected dollar move at DTE
    expected_move_pct   same, as fraction of spot
    pcr_volume          Σ put volume / Σ call volume
    pcr_oi              Σ put OI / Σ call OI

  M1.3 (planned)
    compute_trend_strength    Wilder ADX, normalized to [0, 1] (per §22.5)

  M1.4 (planned)
    classify()          full Market State Engine + 24 regime fixtures

Pure functions. No I/O. No DB. No network. Inputs are simple Python
values + frozen `OptionContract` records; outputs are floats. Edge cases
(insufficient history, degenerate ranges, non-positive prices, missing
expiries) raise `ValueError` — callers absorb staleness per plan §22.12
IV-history validation, which gates `POST /engine/daily-plan` at HTTP 422.
"""

from __future__ import annotations

from engine.market_state.expected_move import expected_move, expected_move_pct
from engine.market_state.hv import compute_hv
from engine.market_state.iv import iv_percentile, iv_rank
from engine.market_state.max_pain import compute_max_pain
from engine.market_state.pcr import pcr_oi, pcr_volume

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
]
