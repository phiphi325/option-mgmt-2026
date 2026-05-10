"""Black-Scholes Greeks for European options with continuous dividend yield.

Per plan v1.2 §9 (Greeks module) and §17 M1.6.

Implements the standard Black-Scholes-Merton Greeks. Inputs flow in as
plain scalars (not `OptionContract` records) so callers can compute
Greeks for hypothetical strikes that aren't in the chain — useful for
the M1.8 Strike Selector and the Phase 1.5 E1 GEX module
(per [ADR-0008](../decisions/0008-enhancement-adoption-roadmap.md)).

Time-to-expiry convention:

    τ = max((expiry − as_of).days, 1) / 365.0

i.e. **calendar days / 365**, with a 1-day floor for expiration-day
chains. This matches the CBOE / OCC convention used by the typical
equity-option data feed providers we expect to plug in at Phase 1.5.

The 1-day floor is a defensive choice. On expiration day τ = 0 produces
a divide-by-zero in d1, but in practice the engine should not see τ ≤ 0
contracts (the data layer filters expired contracts upstream). The floor
covers the corner case of an `as_of` date that lands exactly on an expiry
date — common when CI fixtures freeze the clock.

All Greeks are returned in their natural units:

    delta:  per 1-unit underlying move (e.g. 0.5 = ATM call)
    gamma:  per 1-unit underlying move (interpreted as delta sensitivity)
    vega:   per 1-unit IV change (e.g. divide by 100 for "per 1% IV")
    theta:  per year (divide by 365 for "per day")
    rho:    per 1-unit interest-rate change (divide by 100 for "per 1%")

Pure functions per ADR-0005 — no I/O, no DB, no clock, no env.
"""

from __future__ import annotations

import math
from datetime import date

from engine.types import OptionType

# Calendar days per year for τ. CBOE / OCC convention.
_DAYS_PER_YEAR: float = 365.0

# τ floor in days. On expiration day (τ_raw = 0) BS Greeks are undefined
# (the time-decay term blows up); a 1-day floor keeps the math defined
# without materially affecting non-expiry-day calculations.
_TAU_FLOOR_DAYS: float = 1.0


def time_to_expiry_years(*, as_of: date, expiry: date) -> float:
    """Year-fraction time to expiry using the CBOE 365-day convention.

    Args:
        as_of: Date of valuation.
        expiry: Option expiration date.

    Returns:
        τ in years. Floored at `1/365` to keep BS math defined when
        `as_of == expiry` (or `as_of > expiry`).
    """
    days = (expiry - as_of).days
    return max(float(days), _TAU_FLOOR_DAYS) / _DAYS_PER_YEAR


def _norm_cdf(x: float) -> float:
    """Standard normal CDF via `math.erf`. Stdlib-only (no scipy)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    """Standard normal PDF."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _validate_inputs(
    *,
    spot: float,
    strike: float,
    tau: float,
    iv: float,
) -> None:
    """Common input validation shared by all Greeks functions."""
    if spot <= 0.0:
        raise ValueError(f"greeks: spot must be > 0; got {spot}")
    if strike <= 0.0:
        raise ValueError(f"greeks: strike must be > 0; got {strike}")
    if tau <= 0.0:
        raise ValueError(f"greeks: tau must be > 0; got {tau}")
    if iv <= 0.0:
        raise ValueError(f"greeks: iv must be > 0; got {iv}")


def _d1(
    *,
    spot: float,
    strike: float,
    tau: float,
    iv: float,
    r: float,
    q: float,
) -> float:
    """Black-Scholes-Merton d1 = (ln(S/K) + (r − q + σ²/2)τ) / (σ √τ)."""
    return (
        math.log(spot / strike) + (r - q + 0.5 * iv * iv) * tau
    ) / (iv * math.sqrt(tau))


def _d2_from_d1(d1: float, *, iv: float, tau: float) -> float:
    """Black-Scholes-Merton d2 = d1 − σ √τ."""
    return d1 - iv * math.sqrt(tau)


def delta(
    *,
    spot: float,
    strike: float,
    tau: float,
    iv: float,
    r: float,
    q: float,
    option_type: OptionType,
) -> float:
    """Delta — sensitivity of price to a 1-unit underlying move.

    Call: `Δ_c = e^(−qτ) · N(d1)` in `(0, 1)`.
    Put:  `Δ_p = −e^(−qτ) · N(−d1)` in `(−1, 0)`.

    Returns:
        Δ for the given `option_type`. The standard equity-option
        convention: call deltas positive, put deltas negative.
    """
    _validate_inputs(spot=spot, strike=strike, tau=tau, iv=iv)
    d1 = _d1(spot=spot, strike=strike, tau=tau, iv=iv, r=r, q=q)
    discount_q = math.exp(-q * tau)
    if option_type is OptionType.CALL:
        return discount_q * _norm_cdf(d1)
    return -discount_q * _norm_cdf(-d1)


def gamma(
    *,
    spot: float,
    strike: float,
    tau: float,
    iv: float,
    r: float,
    q: float,
) -> float:
    """Gamma — second derivative of price w.r.t. underlying.

    Identical for calls and puts under BSM:
        `Γ = e^(−qτ) · n(d1) / (S · σ · √τ)`
    """
    _validate_inputs(spot=spot, strike=strike, tau=tau, iv=iv)
    d1 = _d1(spot=spot, strike=strike, tau=tau, iv=iv, r=r, q=q)
    return math.exp(-q * tau) * _norm_pdf(d1) / (spot * iv * math.sqrt(tau))


def vega(
    *,
    spot: float,
    strike: float,
    tau: float,
    iv: float,
    r: float,
    q: float,
) -> float:
    """Vega — sensitivity of price to a 1-unit IV change.

    Identical for calls and puts under BSM:
        `ν = S · e^(−qτ) · n(d1) · √τ`

    Divide by 100 for "per 1% IV change" (the convention most
    risk-management UIs display).
    """
    _validate_inputs(spot=spot, strike=strike, tau=tau, iv=iv)
    d1 = _d1(spot=spot, strike=strike, tau=tau, iv=iv, r=r, q=q)
    return spot * math.exp(-q * tau) * _norm_pdf(d1) * math.sqrt(tau)


def theta(
    *,
    spot: float,
    strike: float,
    tau: float,
    iv: float,
    r: float,
    q: float,
    option_type: OptionType,
) -> float:
    """Theta — sensitivity of price to passage of time (per year).

    Call:
        `Θ_c = −S e^(−qτ) n(d1) σ / (2 √τ)`
        `    − r K e^(−rτ) N(d2)`
        `    + q S e^(−qτ) N(d1)`
    Put:
        `Θ_p = −S e^(−qτ) n(d1) σ / (2 √τ)`
        `    + r K e^(−rτ) N(−d2)`
        `    − q S e^(−qτ) N(−d1)`

    Returned per **year**. Divide by 365 for "per calendar day" or by
    252 for "per trading day" depending on caller convention.
    """
    _validate_inputs(spot=spot, strike=strike, tau=tau, iv=iv)
    d1 = _d1(spot=spot, strike=strike, tau=tau, iv=iv, r=r, q=q)
    d2 = _d2_from_d1(d1, iv=iv, tau=tau)
    discount_q = math.exp(-q * tau)
    discount_r = math.exp(-r * tau)

    decay = -(spot * discount_q * _norm_pdf(d1) * iv) / (2.0 * math.sqrt(tau))
    if option_type is OptionType.CALL:
        return decay - r * strike * discount_r * _norm_cdf(d2) + q * spot * discount_q * _norm_cdf(d1)
    return decay + r * strike * discount_r * _norm_cdf(-d2) - q * spot * discount_q * _norm_cdf(-d1)


def rho(
    *,
    spot: float,
    strike: float,
    tau: float,
    iv: float,
    r: float,
    q: float,
    option_type: OptionType,
) -> float:
    """Rho — sensitivity of price to a 1-unit risk-free-rate change.

    Call: `ρ_c = K τ e^(−rτ) N(d2)`.
    Put:  `ρ_p = −K τ e^(−rτ) N(−d2)`.

    Divide by 100 for "per 1% rate change."
    """
    _validate_inputs(spot=spot, strike=strike, tau=tau, iv=iv)
    d1 = _d1(spot=spot, strike=strike, tau=tau, iv=iv, r=r, q=q)
    d2 = _d2_from_d1(d1, iv=iv, tau=tau)
    discount_r = math.exp(-r * tau)
    if option_type is OptionType.CALL:
        return strike * tau * discount_r * _norm_cdf(d2)
    return -strike * tau * discount_r * _norm_cdf(-d2)
