"""Futures-basis primitive (V1 stub).

Per plan v1.2 §9.3 step 5 (bias mapping) and §9.3a.

`futures_basis` measures the premium / discount of the front-month
equity-index futures vs the underlying spot. Positive basis (futures
above spot) → bullish flow; negative basis (futures below spot) →
bearish flow.

**V1 stub.** Phase 1 of option-mgmt-2026 does not provision futures
data — `apps/api/app/services/futures_service.py` lands in Phase 2.
The §9.3a formula explicitly contemplates this: "0 if futures
unavailable." This V1 stub honors that contract and returns `0.0`.

When the futures service lands, this stub is replaced by:

  1. Look up the front-month equity-index future for the underlying's
     correlated index (e.g. MSFT → ES front-month).
  2. `basis = (futures_price - spot) / spot`.
  3. Return `basis` clipped to a sensible range (e.g. ±5%).

The §9.3a Flow Score formula uses `basis` in both flow sums:

    bullish_score includes `0.15 * max(0,  basis)`   (futures up = bullish)
    bearish_score includes `0.15 * max(0, -basis)`   (futures down = bearish)

With the V1 stub returning 0, both contributions are 0. Both flow
scores fall back accordingly. The full 5-component math activates the
moment Phase 2 wires up the futures service.

Pure function (per ADR-0005).
"""

from __future__ import annotations


def futures_basis(*, spot: float) -> float:
    """Futures-basis fraction (V1 stub — returns 0).

    Args:
        spot: Current underlying spot. Unused in V1. Kept so the
              signature matches the eventual Phase 2 version.

    Returns:
        `0.0` in V1. When Phase 2 ships the futures service, the real
        basis (typically ±0.5% for equity-index futures absent
        dividends or events).

    Raises:
        ValueError: `spot` <= 0. Validates eagerly so callers catch bad
                    input regardless of whether the stub is active.
    """
    if spot <= 0.0:
        raise ValueError(f"futures_basis: spot must be > 0; got {spot}")
    return 0.0
