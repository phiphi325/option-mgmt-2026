"""Fill-confidence scoring + order-type suggestion.

Per plan v1.2 §9.8.

`fill_confidence` is the per-leg [0, 1] estimate that the order will
fill within the suggested limit-price band:

    fill_confidence = clip01(0.6 × liquidity + 0.4 × (1 − spread_bps / 300))

Higher liquidity → higher confidence; tighter spread → higher
confidence. The 0.6/0.4 weights are V1 priors (per §9.8); Phase 4 ML
may calibrate against realized fills.

The order-type suggestion is a threshold rule:

    fill_confidence ≥ 0.70  →  LIMIT (be patient)
    fill_confidence < 0.70  →  MARKETABLE_LIMIT (cross the spread)

Both thresholds (0.70 for LIMIT, 0.50 for the M1.12 downgrade callback)
are V1 priors documented inline as constants.
"""

from __future__ import annotations

from engine._utils import clip01
from engine.execution.types import OrderType

# Per-leg fill weights — locked V1 priors per §9.8.
_W_LIQUIDITY: float = 0.6
_W_SPREAD: float = 0.4

# Spread cap mirrors `engine.execution.liquidity._SPREAD_CAP_BPS` —
# spreads at or above the cap contribute 0 to the spread term.
_SPREAD_CAP_BPS: int = 300

# Confidence threshold below which we switch from passive LIMIT
# to aggressive MARKETABLE_LIMIT. V1 prior — Phase 4 ML may learn it.
_LIMIT_THRESHOLD: float = 0.70

# Aggregate-level threshold for the M1.12 downgrade callback. When
# `aggregate_fill_confidence < 0.50`, the Master Decision Engine
# re-runs the Strike Selector with adjusted filters (e.g. step closer
# to ATM, where liquidity is typically deeper).
DOWNGRADE_THRESHOLD: float = 0.50


def fill_confidence(
    *,
    liquidity: float,
    spread_bps: int,
) -> float:
    """Per-leg fill confidence per plan §9.8.

    Args:
        liquidity:   The leg's `liquidity_score` (already in `[0, 1]`).
        spread_bps:  The leg's spread in basis points of mid. Spreads at
                     or above 300 bps contribute 0 to the spread term.

    Returns:
        `[0, 1]` confidence that the order fills within the suggested
        limit-price band.
    """
    spread_component = 1.0 - min(spread_bps, _SPREAD_CAP_BPS) / float(_SPREAD_CAP_BPS)
    return clip01(_W_LIQUIDITY * liquidity + _W_SPREAD * spread_component)


def suggested_order_type(fill_conf: float) -> OrderType:
    """Threshold rule mapping fill confidence → order type.

    `fill_confidence ≥ 0.70` → `LIMIT` (patient).
    `fill_confidence  < 0.70` → `MARKETABLE_LIMIT` (cross the spread).
    """
    return OrderType.LIMIT if fill_conf >= _LIMIT_THRESHOLD else OrderType.MARKETABLE_LIMIT
