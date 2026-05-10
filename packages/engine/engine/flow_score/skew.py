"""25-delta IV skew primitive (V1 stub).

Per plan v1.2 §9.3 step 3 and §17 M1.5b.

The 25-delta skew is `IV(25-delta put) - IV(25-delta call)` averaged
across the focus expiries. Positive = put-side fear premium (bearish
flow); negative = call-side premium (bullish flow).

**V1 stub.** The proper 25-delta strike identification requires
Black–Scholes delta, which lands in M1.6. Until then, this function
returns `0.0` for any input.

When M1.6 ships, this stub is replaced by a real implementation that:

  1. For each expiry in focus, computes `forward_price = spot * exp(r * τ)`
     (or uses spot if `r ≈ 0`).
  2. Walks the strike grid to find the strike where `|BS delta| ≈ 0.25`
     for each side (put / call), interpolating between strikes when
     necessary.
  3. Looks up IV at those strikes.
  4. `skew = avg over expiries of (iv_put_25d - iv_call_25d)`.

The §9.3a Flow Score formula uses `skew` in both bullish and bearish
weighted sums:

    bullish_score includes `0.20 * max(0, -skew)`   (negative skew = bullish)
    bearish_score includes `0.20 * max(0,  skew)`   (positive skew = bearish)

With the V1 stub returning 0, both contributions are 0. The two flow
scores fall back to a 4-component blend (3 active components when
futures_basis is also stubbed at 0). The full 5-component math
activates the moment this stub is replaced — no recalibration needed.

Pure function (per ADR-0005).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from engine.types import OptionContract


def skew_25d(
    *,
    contracts: Sequence[OptionContract],
    expiry_focus: Sequence[date],
) -> float:
    """25-delta IV skew (V1 stub — returns 0).

    Args:
        contracts: Option-chain contracts. Unused in V1 (the stub does
                   not inspect the chain). The argument is kept so the
                   signature matches the eventual M1.6-backed version
                   and callers don't need to change.
        expiry_focus: Expiry dates to consider. Unused in V1.

    Returns:
        `0.0` in V1. When M1.6 lands, the real 25-delta skew (typical
        values: -0.05 to +0.10 for equity index ETFs; somewhat wider
        for single names around events).
    """
    _ = contracts, expiry_focus  # silence unused-arg linters
    return 0.0
