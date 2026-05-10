"""25-delta IV skew primitive.

Per plan v1.2 §9.3 step 3 (skew component), §9.3a, and §17 M1.6.

The §9.3a Flow Score formula uses

    skew = avg over expiries of IV(25-Δ put) − IV(25-Δ call)

The 25-delta strikes are computed using the Black-Scholes-Merton delta
with each contract's own implied volatility (i.e. the empirical "smile"
is honored: each strike has its own IV, and the 25-Δ strike is the strike
whose BS delta — given its own IV — is closest to ±0.25).

Positive skew → put-side rich → bearish flow.
Negative skew → call-side rich → bullish flow.

The 0.20 weight on `skew` in the §9.3a formula enters both the bullish
and bearish flow sums via `max(0, -skew)` and `max(0, +skew)` respectively
(see `engine.flow_score.compute`).

Pure function (per ADR-0005). No I/O. Depends only on `engine.greeks`,
`engine.types`, and stdlib.

History
-------
M1.5b shipped a V1 stub returning 0.0 because real 25-delta strike
identification requires Black-Scholes delta and the Greeks module had
not yet landed. M1.6 ships `engine.greeks` and replaces the stub with
the real implementation here. **The function signature changed in M1.6**
— callers now must pass `spot` and `as_of`, and may optionally pass
`risk_free_rate` and `dividend_yield` (which default to typical V1
priors). `compute()` was updated to thread these through.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from engine.greeks import delta, time_to_expiry_years
from engine.types import OptionContract, OptionType

# 25-delta targets. Call deltas are positive; put deltas are negative.
_CALL_DELTA_TARGET: float = 0.25
_PUT_DELTA_TARGET: float = -0.25

# V1 calibration priors for `r` and `q` when the caller does not override.
# 5% risk-free rate roughly matches the early-2026 SOFR baseline.
# 0% dividend yield is a reasonable default for MSFT-class names; broad-
# index callers should override with the actual continuous dividend yield.
_DEFAULT_RISK_FREE_RATE: float = 0.05
_DEFAULT_DIVIDEND_YIELD: float = 0.0


def skew_25d(
    *,
    contracts: Sequence[OptionContract],
    expiry_focus: Sequence[date],
    spot: float,
    as_of: date,
    risk_free_rate: float = _DEFAULT_RISK_FREE_RATE,
    dividend_yield: float = _DEFAULT_DIVIDEND_YIELD,
) -> float:
    """Average 25-delta IV skew across focus expiries.

    Args:
        contracts: All option contracts available. Contracts outside
            `expiry_focus`, with missing/zero IV, or at expired τ are
            filtered out internally.
        expiry_focus: The expirations to read. The skew is the average
            across the qualifying expiries.
        spot: Current underlying price. Used to compute BS delta.
        as_of: Date of valuation. Used to compute `τ` for each expiry.
        risk_free_rate: Continuous-compounding risk-free rate. Default
            `0.05` (V1 prior matching the early-2026 SOFR baseline).
            Pass the actual rate when calling from a context that knows
            it.
        dividend_yield: Continuous-compounding dividend yield. Default
            `0.0` (sensible for MSFT-class names). Broad-index callers
            should override.

    Returns:
        Average `IV(25-Δ put) − IV(25-Δ call)` across qualifying focus
        expiries. `0.0` if no expiry has both qualifying calls and puts.

    Raises:
        ValueError: `spot <= 0`.

    Edge cases:
        - Empty `expiry_focus` → 0.0.
        - An expiry has no contracts with valid IV → that expiry is
          skipped, no error.
        - An expiry has only calls or only puts → skipped (skew is
          undefined without both wings).
        - All contracts at an expiry have the same IV → that expiry
          contributes 0 (flat smile).
    """
    if spot <= 0.0:
        raise ValueError(f"skew_25d: spot must be > 0; got {spot}")

    focus = set(expiry_focus)
    if not focus:
        return 0.0

    per_expiry_skews: list[float] = []
    for expiry in sorted(focus):
        tau = time_to_expiry_years(as_of=as_of, expiry=expiry)
        if tau <= 0.0:  # pragma: no cover  (floored at 1/365 by helper)
            continue

        # Filter to contracts at this expiry with positive IV. (The
        # OptionContract schema permits `iv=None` and `iv=0`, both of
        # which are unusable for BS delta.)
        eligible = [
            c
            for c in contracts
            if c.expiry == expiry and c.iv is not None and c.iv > 0.0
        ]
        calls = [c for c in eligible if c.option_type is OptionType.CALL]
        puts = [c for c in eligible if c.option_type is OptionType.PUT]
        if not calls or not puts:
            continue

        # Find 25-delta call: minimize |Δ_c − 0.25|. Tie-break by lower
        # strike for determinism. We materialize `(distance, strike, contract)`
        # tuples eagerly inside the loop body — this avoids the late-binding
        # closure-over-loop-variable footgun (ruff B023) that arises if the
        # `key` function captures `tau` lexically.
        call_dists = [
            (
                abs(
                    delta(
                        spot=spot,
                        strike=c.strike,
                        tau=tau,
                        iv=c.iv if c.iv is not None else 0.0,
                        r=risk_free_rate,
                        q=dividend_yield,
                        option_type=OptionType.CALL,
                    )
                    - _CALL_DELTA_TARGET
                ),
                c.strike,
                c,
            )
            for c in calls
        ]
        put_dists = [
            (
                abs(
                    delta(
                        spot=spot,
                        strike=c.strike,
                        tau=tau,
                        iv=c.iv if c.iv is not None else 0.0,
                        r=risk_free_rate,
                        q=dividend_yield,
                        option_type=OptionType.PUT,
                    )
                    - _PUT_DELTA_TARGET
                ),
                c.strike,
                c,
            )
            for c in puts
        ]
        call_25d = min(call_dists, key=lambda t: (t[0], t[1]))[2]
        put_25d = min(put_dists, key=lambda t: (t[0], t[1]))[2]

        # mypy: iv is `float | None` on `OptionContract`; we filtered to
        # `iv > 0` above so the asserts are statically obvious but mypy
        # can't see through the filter.
        assert call_25d.iv is not None and put_25d.iv is not None  # noqa: S101
        per_expiry_skews.append(put_25d.iv - call_25d.iv)

    if not per_expiry_skews:
        return 0.0
    return sum(per_expiry_skews) / len(per_expiry_skews)
