"""Size warnings + tick-aware limit-price-band helpers.

Per plan v1.2 §9.8 (which references `size_warnings(q, a.qty)` and a
`limit_price_band` derived from `tick(q)` but doesn't spell them out).

Two helpers:

  - `tick_size(mid)` — US options tick: $0.01 for mid < $3, $0.05 above.
  - `limit_price_band(bid, ask, mid)` — `(mid − tick, mid + tick)`.
  - `size_warnings(oi, volume, qty)` — heuristic "your order is too big
    for this strike" warnings the UI surfaces.

V1 prior thresholds:
  - `qty > 0.10 × OI`      → "qty exceeds 10% of OI"
  - `qty > 0.50 × volume`  → "qty exceeds 50% of daily volume"

These are heuristics, not hard blocks — the UI shows them so the user
can adjust before submitting. The M1.12 downgrade callback uses the
aggregate `fill_confidence` threshold (0.50), not these warnings.
"""

from __future__ import annotations

# US options tick boundaries (per SEC rule 612 / exchange rules):
# $0.01 for premiums below $3.00; $0.05 above. Some pilots / classes
# differ; the V1 default is the standard rule.
_TICK_THRESHOLD_DOLLARS: float = 3.0
_TICK_BELOW: float = 0.01
_TICK_ABOVE: float = 0.05

# Size-warning thresholds — V1 priors.
_OI_WARNING_FRACTION: float = 0.10
_VOLUME_WARNING_FRACTION: float = 0.50


def tick_size(mid: float) -> float:
    """US-options tick size for a given mid price.

    Returns `0.01` for `mid < $3`, else `0.05`.
    """
    return _TICK_BELOW if mid < _TICK_THRESHOLD_DOLLARS else _TICK_ABOVE


def limit_price_band(
    *,
    bid: float | None,
    ask: float | None,
    mid: float | None,
) -> tuple[float, float]:
    """Suggested limit-price band of width ±1 tick around mid.

    Args:
        bid:  Quote bid. Used as a fallback when `mid` is missing.
        ask:  Quote ask. Used as a fallback when `mid` is missing.
        mid:  Quote mid. Falls back to `(bid + ask) / 2` when `None`.

    Returns:
        `(low, high)` floats. When the quote is entirely broken
        (no bid/ask/mid), returns `(0.0, 0.0)` as a safe sentinel.
        Low is clamped to 0 (negative prices don't make sense for
        bought options).
    """
    if mid is None:
        if bid is None or ask is None:
            return (0.0, 0.0)
        mid = (bid + ask) / 2.0
    t = tick_size(mid)
    low = max(mid - t, 0.0)
    high = mid + t
    return (low, high)


def size_warnings(
    *,
    oi: int,
    volume: int,
    qty: int,
) -> tuple[str, ...]:
    """Heuristic "your order is large relative to displayed liquidity" warnings.

    Returns a tuple of human-readable strings (possibly empty).

    Triggers:
      - qty > 0.10 × OI       → "qty {qty} exceeds 10% of open interest ({oi}); price impact likely"
      - qty > 0.50 × volume   → "qty {qty} exceeds 50% of daily volume ({volume}); fill may be slow"
    """
    warnings: list[str] = []
    qty_abs = abs(qty)
    if qty_abs <= 0:
        return ()

    if oi > 0 and qty_abs > _OI_WARNING_FRACTION * oi:
        warnings.append(
            f"qty {qty_abs} exceeds {int(_OI_WARNING_FRACTION * 100)}% "
            f"of open interest ({oi}); price impact likely"
        )
    if volume > 0 and qty_abs > _VOLUME_WARNING_FRACTION * volume:
        warnings.append(
            f"qty {qty_abs} exceeds {int(_VOLUME_WARNING_FRACTION * 100)}% "
            f"of daily volume ({volume}); fill may be slow"
        )
    return tuple(warnings)
