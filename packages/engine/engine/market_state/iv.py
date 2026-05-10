"""IV Rank and IV Percentile primitives.

Per plan v1.2 §9.1 (Market State Engine inputs) and §22.12 (IV history
validation policy: hard 422 below 30 observations, warn below 60, info
below 252).

Both functions take a sequence of historical IV values (typically ATM 30d
IV, ordered oldest to newest) plus the *current* IV. They return a unit
interval [0, 1] score.

  iv_rank        Range-based: where does current IV sit between the
                 historical min and max? Linear between, clipped on
                 extremes. Sensitive to outliers (one IV spike pulls the
                 max up, suppressing the rank for the rest of the series),
                 but the rank corresponds directly to "where in the band
                 are we" which is the natural premium-selling intuition.

  iv_percentile  Count-based: what fraction of historical observations
                 are strictly *below* the current IV? 0.5 = median.
                 Robust to outliers but insensitive to magnitude (a 1%
                 IV jump and a 30% IV jump can both register as the same
                 percentile if the historical distribution is dense).

For premium-selling decisions, the M1.4 Market State Engine + M1.4a
`iv_score()` weight both signals. They're complementary, not redundant.

Edge cases:

  - Insufficient history (< 30 observations) → `ValueError`. Caller is
    responsible for staleness handling (per §22.12).
  - Constant history (max == min) → `iv_rank` returns 0.5 (no signal);
    `iv_percentile` returns the natural count-based answer.
  - Out-of-range current IV → `iv_rank` clips to [0, 1]; `iv_percentile`
    can return 0.0 (current below all observations) or 1.0 (current above
    all observations) cleanly.
"""

from __future__ import annotations

from collections.abc import Sequence

# Plan v1.2 §22.12 — minimum history for IV rank/percentile.
# `POST /data/iv/import-csv` returns level=block under this threshold.
MIN_IV_HISTORY = 30


def iv_rank(*, current_iv: float, history: Sequence[float]) -> float:
    """Range-based IV rank in `[0, 1]`.

    Returns `(current - min) / (max - min)` over the history, clipped to the
    unit interval. When the historical range is degenerate (max == min),
    returns 0.5 — the "no information" prior. Callers needing to distinguish
    "rank is 0.5 because we're at the median" from "rank is 0.5 because
    history is constant" should inspect the history themselves.
    """
    n = len(history)
    if n < MIN_IV_HISTORY:
        raise ValueError(
            f"iv_rank requires >= {MIN_IV_HISTORY} observations of IV "
            f"history (per plan v1.2 §22.12); got {n}"
        )
    lo = min(history)
    hi = max(history)
    if hi <= lo:
        return 0.5
    raw = (current_iv - lo) / (hi - lo)
    if raw < 0.0:
        return 0.0
    if raw > 1.0:
        return 1.0
    return raw


def iv_percentile(*, current_iv: float, history: Sequence[float]) -> float:
    """Count-based IV percentile in `[0, 1]`.

    Returns the fraction of historical observations strictly less than
    `current_iv`. Ties at `current_iv` are NOT counted, so the median of a
    sorted unique series with N elements gives 0.5 when current equals the
    `(N // 2)`-th element. For dense or repeated series this is a stable,
    coarse signal.
    """
    n = len(history)
    if n < MIN_IV_HISTORY:
        raise ValueError(
            f"iv_percentile requires >= {MIN_IV_HISTORY} observations "
            f"(per plan v1.2 §22.12); got {n}"
        )
    n_below = sum(1 for x in history if x < current_iv)
    return n_below / n
