"""Market State scoring primitives.

Per plan v1.2 §9.1 (Market State Engine inputs) and §17 M1.1.

This sub-package provides the **scoring primitives** consumed by the full
Market State Engine (M1.4): IV rank, IV percentile, and historical
volatility (HV).

Pure functions. No I/O. No DB. No network. Inputs are sequences of floats;
outputs are floats. Edge cases (insufficient history, degenerate ranges,
non-positive prices) raise `ValueError` — callers are responsible for
validating + surfacing staleness or "blocked" states (per plan §22.12 IV
history validation, which gates `POST /engine/daily-plan` at HTTP 422 below
30 observations).

The full Market State Engine (with `classify()`, regime determination, and
24 regime fixtures) ships in M1.4 and consumes these primitives. M1.1's
scope is the primitives and their tests; M1.2 adds max pain + expected move
+ PCR; M1.3 adds trend strength (Wilder ADX); M1.4 wires them all into the
regime-classifying engine.
"""

from __future__ import annotations

from engine.market_state.hv import compute_hv
from engine.market_state.iv import iv_percentile, iv_rank

__all__ = [
    "compute_hv",
    "iv_percentile",
    "iv_rank",
]
