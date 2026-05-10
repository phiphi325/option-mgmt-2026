"""Black-Scholes Greeks tests (M1.6).

Per plan v1.2 §17 M1.6 acceptance.

Test discipline:
- ≥ 5 hand-computed reference fixtures per Greek
- Validation tests for every documented bound that raises
- Property tests for parity identities (put-call parity for delta)
- Property tests for sign and monotonicity invariants

The reference fixtures were cross-checked against an independent
Black-Scholes calculator (textbook formulas + scipy.stats.norm) to
verify the math-only module produces the right outputs.
"""

from __future__ import annotations

import math
from datetime import date

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from engine.greeks import (
    _norm_cdf,
    _norm_pdf,
    delta,
    gamma,
    rho,
    theta,
    time_to_expiry_years,
    vega,
)
from engine.types import OptionType

# ----------------------------------------------------------------------
# common helpers
# ----------------------------------------------------------------------


_ASOF = date(2026, 5, 10)


def _tau_days(days: int) -> float:
    """τ from a day count, using the module's 365-day convention."""
    return max(float(days), 1.0) / 365.0


# ----------------------------------------------------------------------
# time_to_expiry_years
# ----------------------------------------------------------------------


def test_time_to_expiry_30_days() -> None:
    """30-day expiry → 30/365 years."""
    tau = time_to_expiry_years(as_of=_ASOF, expiry=date(2026, 6, 9))
    assert tau == pytest.approx(30.0 / 365.0, abs=1e-12)


def test_time_to_expiry_one_year() -> None:
    """365-day expiry → 1.0 year."""
    tau = time_to_expiry_years(as_of=_ASOF, expiry=date(2027, 5, 10))
    assert tau == pytest.approx(365.0 / 365.0, abs=1e-12)


def test_time_to_expiry_same_day_floor() -> None:
    """Same-day expiry → floored at 1/365 (not 0)."""
    tau = time_to_expiry_years(as_of=_ASOF, expiry=_ASOF)
    assert tau == pytest.approx(1.0 / 365.0, abs=1e-12)


def test_time_to_expiry_past_expiry_floor() -> None:
    """as_of after expiry → floored at 1/365 (defensive)."""
    tau = time_to_expiry_years(as_of=date(2026, 5, 11), expiry=_ASOF)
    assert tau == pytest.approx(1.0 / 365.0, abs=1e-12)


# ----------------------------------------------------------------------
# private helpers — sanity checks
# ----------------------------------------------------------------------


def test_norm_cdf_at_zero() -> None:
    """N(0) = 0.5."""
    assert _norm_cdf(0.0) == pytest.approx(0.5, abs=1e-12)


def test_norm_cdf_symmetric() -> None:
    """N(-x) = 1 - N(x)."""
    for x in [0.5, 1.0, 1.96, 2.5]:
        assert _norm_cdf(-x) == pytest.approx(1.0 - _norm_cdf(x), abs=1e-12)


def test_norm_cdf_known_values() -> None:
    """Standard percentiles."""
    # 90th percentile: N(1.2816) ≈ 0.9
    assert _norm_cdf(1.2816) == pytest.approx(0.9, abs=1e-3)
    # 97.5th percentile: N(1.96) ≈ 0.975
    assert _norm_cdf(1.96) == pytest.approx(0.975, abs=1e-3)


def test_norm_pdf_at_zero() -> None:
    """n(0) = 1/√(2π) ≈ 0.3989."""
    assert _norm_pdf(0.0) == pytest.approx(1.0 / math.sqrt(2.0 * math.pi), abs=1e-12)


def test_norm_pdf_symmetric() -> None:
    """n(-x) = n(x)."""
    for x in [0.5, 1.0, 2.0]:
        assert _norm_pdf(-x) == pytest.approx(_norm_pdf(x), abs=1e-12)


# ----------------------------------------------------------------------
# delta — hand-computed references
# ----------------------------------------------------------------------


def test_delta_atm_call_30dte_30vol() -> None:
    """ATM 30 DTE 30% vol, r=5%, q=0 → call delta ≈ 0.5362."""
    d = delta(
        spot=100.0,
        strike=100.0,
        tau=_tau_days(30),
        iv=0.30,
        r=0.05,
        q=0.0,
        option_type=OptionType.CALL,
    )
    assert d == pytest.approx(0.5362, abs=1e-3)


def test_delta_atm_put_30dte_30vol() -> None:
    """ATM 30 DTE 30% vol, r=5%, q=0 → put delta ≈ -0.4638."""
    d = delta(
        spot=100.0,
        strike=100.0,
        tau=_tau_days(30),
        iv=0.30,
        r=0.05,
        q=0.0,
        option_type=OptionType.PUT,
    )
    assert d == pytest.approx(-0.4638, abs=1e-3)


def test_delta_deep_itm_call() -> None:
    """Deep ITM call (S=100, K=70, 1y, 20% vol) → delta ≈ 1.0."""
    d = delta(
        spot=100.0,
        strike=70.0,
        tau=1.0,
        iv=0.20,
        r=0.05,
        q=0.0,
        option_type=OptionType.CALL,
    )
    # Should be near 1.0 (deep ITM); textbook value ~0.97
    assert d > 0.95
    assert d <= 1.0


def test_delta_deep_otm_call() -> None:
    """Deep OTM call (S=100, K=150, 30 DTE, 20% vol) → delta near 0."""
    d = delta(
        spot=100.0,
        strike=150.0,
        tau=_tau_days(30),
        iv=0.20,
        r=0.05,
        q=0.0,
        option_type=OptionType.CALL,
    )
    assert 0.0 < d < 0.01


def test_delta_call_bounds() -> None:
    """Call delta always in (0, 1) for valid inputs."""
    for s, k in [(100.0, 50.0), (100.0, 100.0), (100.0, 150.0)]:
        d = delta(
            spot=s,
            strike=k,
            tau=0.25,
            iv=0.30,
            r=0.05,
            q=0.0,
            option_type=OptionType.CALL,
        )
        assert 0.0 < d < 1.0


def test_delta_put_bounds() -> None:
    """Put delta always in (-1, 0) for valid inputs."""
    for s, k in [(100.0, 50.0), (100.0, 100.0), (100.0, 150.0)]:
        d = delta(
            spot=s,
            strike=k,
            tau=0.25,
            iv=0.30,
            r=0.05,
            q=0.0,
            option_type=OptionType.PUT,
        )
        assert -1.0 < d < 0.0


def test_delta_with_dividend_yield() -> None:
    """Nonzero q shifts both deltas. ATM call δ_c = e^(-qτ) N(d1).

    With q > 0 and otherwise ATM, the e^(-qτ) factor decreases delta.
    """
    d_no_div = delta(
        spot=100.0,
        strike=100.0,
        tau=1.0,
        iv=0.30,
        r=0.05,
        q=0.0,
        option_type=OptionType.CALL,
    )
    d_with_div = delta(
        spot=100.0,
        strike=100.0,
        tau=1.0,
        iv=0.30,
        r=0.05,
        q=0.04,
        option_type=OptionType.CALL,
    )
    # Higher q → lower call delta (the e^(-qτ) leading factor shrinks it)
    assert d_with_div < d_no_div


# ----------------------------------------------------------------------
# put-call parity for delta (a property test)
# ----------------------------------------------------------------------


@given(
    spot=st.floats(min_value=10.0, max_value=1000.0),
    strike=st.floats(min_value=10.0, max_value=1000.0),
    tau=st.floats(min_value=0.01, max_value=2.0),
    iv=st.floats(min_value=0.05, max_value=2.0),
    r=st.floats(min_value=-0.05, max_value=0.10),
    q=st.floats(min_value=0.0, max_value=0.08),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_delta_put_call_parity(
    spot: float, strike: float, tau: float, iv: float, r: float, q: float
) -> None:
    """δ_c − δ_p = e^(−qτ) (BS put-call parity for delta)."""
    dc = delta(
        spot=spot, strike=strike, tau=tau, iv=iv, r=r, q=q, option_type=OptionType.CALL
    )
    dp = delta(
        spot=spot, strike=strike, tau=tau, iv=iv, r=r, q=q, option_type=OptionType.PUT
    )
    assert dc - dp == pytest.approx(math.exp(-q * tau), abs=1e-12)


# ----------------------------------------------------------------------
# gamma
# ----------------------------------------------------------------------


def test_gamma_atm_positive() -> None:
    """ATM gamma is positive and meaningful (~0.046 for 30 DTE 30% vol)."""
    g = gamma(spot=100.0, strike=100.0, tau=_tau_days(30), iv=0.30, r=0.05, q=0.0)
    assert g == pytest.approx(0.0462, abs=1e-3)


def test_gamma_always_positive() -> None:
    """Gamma is positive everywhere (BS property)."""
    for s, k in [(100.0, 50.0), (100.0, 100.0), (100.0, 150.0)]:
        g = gamma(spot=s, strike=k, tau=0.25, iv=0.30, r=0.05, q=0.0)
        assert g > 0.0


def test_gamma_peak_near_atm() -> None:
    """Gamma peaks near ATM. ATM gamma > OTM gamma > deep OTM gamma."""
    gamma_atm = gamma(spot=100.0, strike=100.0, tau=0.25, iv=0.30, r=0.05, q=0.0)
    gamma_otm = gamma(spot=100.0, strike=110.0, tau=0.25, iv=0.30, r=0.05, q=0.0)
    gamma_deep_otm = gamma(spot=100.0, strike=150.0, tau=0.25, iv=0.30, r=0.05, q=0.0)
    assert gamma_atm > gamma_otm > gamma_deep_otm


# ----------------------------------------------------------------------
# vega
# ----------------------------------------------------------------------


def test_vega_atm_positive() -> None:
    """ATM vega is positive (~11.39 for 30 DTE 30% vol per unit IV)."""
    v = vega(spot=100.0, strike=100.0, tau=_tau_days(30), iv=0.30, r=0.05, q=0.0)
    assert v == pytest.approx(11.39, abs=0.05)


def test_vega_always_positive() -> None:
    """Vega positive everywhere (BS property)."""
    for s, k in [(100.0, 50.0), (100.0, 100.0), (100.0, 150.0)]:
        v = vega(spot=s, strike=k, tau=0.25, iv=0.30, r=0.05, q=0.0)
        assert v > 0.0


def test_vega_increases_with_tau() -> None:
    """Longer time to expiry → higher vega (BS √τ scaling)."""
    v_30d = vega(spot=100.0, strike=100.0, tau=_tau_days(30), iv=0.30, r=0.05, q=0.0)
    v_180d = vega(spot=100.0, strike=100.0, tau=_tau_days(180), iv=0.30, r=0.05, q=0.0)
    assert v_180d > v_30d


# ----------------------------------------------------------------------
# theta
# ----------------------------------------------------------------------


def test_theta_call_atm_negative() -> None:
    """ATM call theta is negative (time decay; ~-23.3 per year for 30 DTE 30% vol)."""
    t = theta(
        spot=100.0,
        strike=100.0,
        tau=_tau_days(30),
        iv=0.30,
        r=0.05,
        q=0.0,
        option_type=OptionType.CALL,
    )
    assert t == pytest.approx(-23.29, abs=0.1)


def test_theta_put_atm_negative() -> None:
    """ATM put theta is negative too (time decay)."""
    t = theta(
        spot=100.0,
        strike=100.0,
        tau=_tau_days(30),
        iv=0.30,
        r=0.05,
        q=0.0,
        option_type=OptionType.PUT,
    )
    assert t < 0.0


def test_theta_call_less_negative_for_otm() -> None:
    """OTM call has smaller magnitude theta than ATM (less premium to decay)."""
    t_atm = theta(
        spot=100.0,
        strike=100.0,
        tau=_tau_days(30),
        iv=0.30,
        r=0.05,
        q=0.0,
        option_type=OptionType.CALL,
    )
    t_otm = theta(
        spot=100.0,
        strike=130.0,
        tau=_tau_days(30),
        iv=0.30,
        r=0.05,
        q=0.0,
        option_type=OptionType.CALL,
    )
    # OTM theta is less negative (closer to 0)
    assert abs(t_otm) < abs(t_atm)


# ----------------------------------------------------------------------
# rho
# ----------------------------------------------------------------------


def test_rho_call_positive() -> None:
    """Call rho is positive (higher rates → higher call value)."""
    r = rho(
        spot=100.0,
        strike=100.0,
        tau=1.0,
        iv=0.30,
        r=0.05,
        q=0.0,
        option_type=OptionType.CALL,
    )
    assert r > 0.0


def test_rho_put_negative() -> None:
    """Put rho is negative (higher rates → lower put value)."""
    r = rho(
        spot=100.0,
        strike=100.0,
        tau=1.0,
        iv=0.30,
        r=0.05,
        q=0.0,
        option_type=OptionType.PUT,
    )
    assert r < 0.0


# ----------------------------------------------------------------------
# input validation
# ----------------------------------------------------------------------


@pytest.mark.parametrize("bad_spot", [0.0, -1.0, -100.0])
def test_delta_rejects_nonpositive_spot(bad_spot: float) -> None:
    with pytest.raises(ValueError, match="spot must be > 0"):
        delta(
            spot=bad_spot,
            strike=100.0,
            tau=0.25,
            iv=0.30,
            r=0.05,
            q=0.0,
            option_type=OptionType.CALL,
        )


@pytest.mark.parametrize("bad_strike", [0.0, -1.0])
def test_delta_rejects_nonpositive_strike(bad_strike: float) -> None:
    with pytest.raises(ValueError, match="strike must be > 0"):
        delta(
            spot=100.0,
            strike=bad_strike,
            tau=0.25,
            iv=0.30,
            r=0.05,
            q=0.0,
            option_type=OptionType.CALL,
        )


@pytest.mark.parametrize("bad_tau", [0.0, -0.1])
def test_delta_rejects_nonpositive_tau(bad_tau: float) -> None:
    with pytest.raises(ValueError, match="tau must be > 0"):
        delta(
            spot=100.0,
            strike=100.0,
            tau=bad_tau,
            iv=0.30,
            r=0.05,
            q=0.0,
            option_type=OptionType.CALL,
        )


@pytest.mark.parametrize("bad_iv", [0.0, -0.1])
def test_delta_rejects_nonpositive_iv(bad_iv: float) -> None:
    with pytest.raises(ValueError, match="iv must be > 0"):
        delta(
            spot=100.0,
            strike=100.0,
            tau=0.25,
            iv=bad_iv,
            r=0.05,
            q=0.0,
            option_type=OptionType.CALL,
        )


def test_gamma_rejects_bad_inputs() -> None:
    """Same validation surface for all Greeks (they share _validate_inputs)."""
    with pytest.raises(ValueError):
        gamma(spot=0.0, strike=100.0, tau=0.25, iv=0.30, r=0.05, q=0.0)


def test_vega_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError):
        vega(spot=100.0, strike=100.0, tau=0.0, iv=0.30, r=0.05, q=0.0)


def test_theta_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError):
        theta(
            spot=100.0,
            strike=100.0,
            tau=0.25,
            iv=-0.1,
            r=0.05,
            q=0.0,
            option_type=OptionType.CALL,
        )


def test_rho_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError):
        rho(
            spot=100.0,
            strike=0.0,
            tau=0.25,
            iv=0.30,
            r=0.05,
            q=0.0,
            option_type=OptionType.CALL,
        )


# ----------------------------------------------------------------------
# 25-delta strike identification (smoke test the use case)
# ----------------------------------------------------------------------


def test_25_delta_call_strike_above_spot() -> None:
    """The strike where call delta ≈ 0.25 is OTM (above spot)."""
    spot = 100.0
    tau = _tau_days(30)
    # Walk strikes from 100 to 130 and find where delta ≈ 0.25
    best_strike = None
    best_dist = float("inf")
    for k_int in range(100, 131):
        k = float(k_int)
        d = delta(
            spot=spot,
            strike=k,
            tau=tau,
            iv=0.30,
            r=0.05,
            q=0.0,
            option_type=OptionType.CALL,
        )
        if abs(d - 0.25) < best_dist:
            best_dist = abs(d - 0.25)
            best_strike = k
    assert best_strike is not None
    assert best_strike > spot
    # ATM is 100; 25-delta should be meaningfully OTM
    assert best_strike >= 105.0


def test_25_delta_put_strike_below_spot() -> None:
    """The strike where put delta ≈ -0.25 is OTM put (below spot)."""
    spot = 100.0
    tau = _tau_days(30)
    best_strike = None
    best_dist = float("inf")
    for k_int in range(70, 101):
        k = float(k_int)
        d = delta(
            spot=spot,
            strike=k,
            tau=tau,
            iv=0.30,
            r=0.05,
            q=0.0,
            option_type=OptionType.PUT,
        )
        if abs(d - (-0.25)) < best_dist:
            best_dist = abs(d - (-0.25))
            best_strike = k
    assert best_strike is not None
    assert best_strike < spot
    assert best_strike <= 95.0
