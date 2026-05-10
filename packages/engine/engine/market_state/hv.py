"""Historical Volatility (HV) primitive.

Per plan v1.2 §9.1 (Market State Engine inputs) and §17 M1.1.

HV is the **annualized standard deviation of daily log returns** over a
trailing window. Default lookback is 30 → HV_30, the canonical short-window
realized vol used by:

  - `iv_score()` (M1.4a) — IV vs HV premium signal: positive when implied
    is rich vs realized, the core edge for premium sellers.
  - Market State Engine `classify()` — `realized_vs_implied` gate, used in
    the LOW_IV_TREND vs LOW_IV_RANGE branch of the regime tree.
  - VolPremiumResult (E5, Phase 2 per ADR-0008) — sustains the `IV − HV`
    differential as a premium-percentile metric over trailing 12 months.

Annualization uses 252 trading days per year (consistent with plan v1.2
§9.1 expected-move formula `spot * iv * sqrt(dte/252)` and the §22.5 Wilder
ADX implementation).

Edge cases (the engine raises; callers absorb staleness):

  - Insufficient prices (`len < lookback + 1`) → `ValueError`. M1.4's
    `classify()` should never see this; data ingestion (P2 §22.12) is
    responsible for blocking ingestion below threshold.
  - Non-positive prices → `ValueError`. log of zero or negative is
    undefined; corrupted input should fail loudly.
  - Constant prices → 0.0. Mathematically correct; the Confidence Composer
    and the M1.4a `iv_score()` should treat 0.0 HV as "no realized motion"
    and ignore the IV − HV signal that day.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

# Plan v1.2 §9.1 + §22.5: 252 trading days per year is the canonical
# annualization factor across the engine. Single source of truth.
TRADING_DAYS_PER_YEAR = 252

# Sample standard deviation (Bessel correction). Plan v1.2 doesn't pin this
# but the §9.1 expected-move math and §22.5 Wilder ADX both implicitly treat
# the IV input as a sample estimator. ddof=1 keeps HV on the same footing.
_STD_DDOF = 1


def compute_hv(*, prices: Sequence[float], lookback: int = 30) -> float:
    """Annualized historical volatility from a sequence of close prices.

    Computes log returns over the most-recent `lookback + 1` prices (so
    `lookback` returns enter the calculation), then returns the sample
    standard deviation × `sqrt(252)`.

    Args:
        prices: Sequence of close prices, ordered oldest to newest.
                Must contain at least `lookback + 1` elements.
        lookback: Number of returns to use. Default 30 = HV_30.

    Returns:
        Annualized volatility as a decimal. e.g. 0.22 = 22% annualized.

    Raises:
        ValueError: if fewer than `lookback + 1` prices, or any price is
                    not strictly positive.
    """
    n = len(prices)
    if n < lookback + 1:
        raise ValueError(
            f"compute_hv with lookback={lookback} requires "
            f">= {lookback + 1} prices; got {n}"
        )
    window = prices[-(lookback + 1) :]
    if any(p <= 0 for p in window):
        raise ValueError(
            "compute_hv: prices must be strictly positive (log of "
            "non-positive value is undefined)"
        )

    log_returns = [
        math.log(window[i] / window[i - 1]) for i in range(1, len(window))
    ]
    if len(log_returns) <= _STD_DDOF:
        # Cannot compute a sample std with ddof=1 from <= 1 observation.
        return 0.0

    mean = sum(log_returns) / len(log_returns)
    var_sum = sum((r - mean) ** 2 for r in log_returns)
    sample_var = var_sum / (len(log_returns) - _STD_DDOF)
    daily_vol = math.sqrt(sample_var)
    return daily_vol * math.sqrt(TRADING_DAYS_PER_YEAR)
