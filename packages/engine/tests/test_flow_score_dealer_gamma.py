"""Dealer-gamma-proxy primitive tests (M1.5)."""

from __future__ import annotations

from datetime import date

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from engine.flow_score import compute_dealer_gamma_proxy
from engine.types import OptionContract, OptionType

# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------


_EXPIRY = date(2026, 6, 19)
_FAR_EXPIRY = date(2026, 12, 18)


def _contract(
    *,
    strike: float,
    option_type: OptionType,
    open_interest: int,
    expiry: date = _EXPIRY,
) -> OptionContract:
    return OptionContract(
        underlying="MSFT",
        expiry=expiry,
        strike=strike,
        option_type=option_type,
        open_interest=open_interest,
        volume=0,
    )


# ----------------------------------------------------------------------
# sign convention — hand-computed references
# ----------------------------------------------------------------------


def test_dealer_gamma_call_above_spot_is_negative() -> None:
    """A single call above spot → proxy is negative.

    sign(call) = -1; (K-S) = 110-100 = 10; OI = 1000.
    proxy = -1 · 1000 · 10 = -10000.

    Interpretation: dealer is long this call → short gamma above spot →
    vol amplifier on upside moves.
    """
    contracts = [_contract(strike=110.0, option_type=OptionType.CALL, open_interest=1000)]
    proxy = compute_dealer_gamma_proxy(
        contracts=contracts, spot=100.0, expiry_focus=[_EXPIRY]
    )
    assert proxy == pytest.approx(-10000.0)


def test_dealer_gamma_call_below_spot_is_positive() -> None:
    """A single call below spot → proxy is positive.

    sign(call) = -1; (K-S) = 90-100 = -10; OI = 1000.
    proxy = -1 · 1000 · -10 = +10000.

    Interpretation: dealer long this ITM call below spot → long gamma →
    vol dampener.
    """
    contracts = [_contract(strike=90.0, option_type=OptionType.CALL, open_interest=1000)]
    proxy = compute_dealer_gamma_proxy(
        contracts=contracts, spot=100.0, expiry_focus=[_EXPIRY]
    )
    assert proxy == pytest.approx(+10000.0)


def test_dealer_gamma_put_below_spot_is_negative() -> None:
    """A single put below spot → proxy is negative.

    sign(put) = +1; (K-S) = 90-100 = -10; OI = 1000.
    proxy = +1 · 1000 · -10 = -10000.

    Interpretation: dealer short this OTM put below spot → short gamma →
    vol amplifier on downside moves.
    """
    contracts = [_contract(strike=90.0, option_type=OptionType.PUT, open_interest=1000)]
    proxy = compute_dealer_gamma_proxy(
        contracts=contracts, spot=100.0, expiry_focus=[_EXPIRY]
    )
    assert proxy == pytest.approx(-10000.0)


def test_dealer_gamma_put_above_spot_is_positive() -> None:
    """A single put above spot → proxy is positive.

    sign(put) = +1; (K-S) = 110-100 = 10; OI = 1000.
    proxy = +1 · 1000 · 10 = +10000.
    """
    contracts = [_contract(strike=110.0, option_type=OptionType.PUT, open_interest=1000)]
    proxy = compute_dealer_gamma_proxy(
        contracts=contracts, spot=100.0, expiry_focus=[_EXPIRY]
    )
    assert proxy == pytest.approx(+10000.0)


def test_dealer_gamma_symmetric_chain_is_zero() -> None:
    """Symmetric call/put OI at symmetric strikes → proxy = 0.

    Equal call OI above spot and put OI below spot, mirrored.
    """
    contracts = [
        _contract(strike=90.0, option_type=OptionType.PUT, open_interest=1000),   # -10000
        _contract(strike=110.0, option_type=OptionType.CALL, open_interest=1000),  # -10000
        _contract(strike=90.0, option_type=OptionType.CALL, open_interest=1000),  # +10000
        _contract(strike=110.0, option_type=OptionType.PUT, open_interest=1000),   # +10000
    ]
    proxy = compute_dealer_gamma_proxy(
        contracts=contracts, spot=100.0, expiry_focus=[_EXPIRY]
    )
    assert proxy == pytest.approx(0.0, abs=1e-9)


def test_dealer_gamma_short_gamma_concentration() -> None:
    """Heavy call OI above spot dominates → strongly negative proxy."""
    contracts = [
        _contract(strike=110.0, option_type=OptionType.CALL, open_interest=5000),
        _contract(strike=120.0, option_type=OptionType.CALL, open_interest=3000),
        _contract(strike=90.0, option_type=OptionType.PUT, open_interest=500),
    ]
    # 110 call: -5000 · 10 = -50000
    # 120 call: -3000 · 20 = -60000
    # 90 put:   +500 · -10 = -5000
    # Total = -115000
    proxy = compute_dealer_gamma_proxy(
        contracts=contracts, spot=100.0, expiry_focus=[_EXPIRY]
    )
    assert proxy == pytest.approx(-115000.0)


def test_dealer_gamma_zero_oi_contributes_nothing() -> None:
    """Contracts with zero OI contribute nothing."""
    contracts = [
        _contract(strike=110.0, option_type=OptionType.CALL, open_interest=0),
        _contract(strike=90.0, option_type=OptionType.PUT, open_interest=0),
    ]
    proxy = compute_dealer_gamma_proxy(
        contracts=contracts, spot=100.0, expiry_focus=[_EXPIRY]
    )
    assert proxy == 0.0


def test_dealer_gamma_strike_at_spot_contributes_zero() -> None:
    """A contract with strike == spot contributes 0 (K - S = 0)."""
    contracts = [
        _contract(strike=100.0, option_type=OptionType.CALL, open_interest=10_000),
        _contract(strike=100.0, option_type=OptionType.PUT, open_interest=10_000),
    ]
    proxy = compute_dealer_gamma_proxy(
        contracts=contracts, spot=100.0, expiry_focus=[_EXPIRY]
    )
    assert proxy == 0.0


# ----------------------------------------------------------------------
# expiry filter
# ----------------------------------------------------------------------


def test_dealer_gamma_filters_other_expiries() -> None:
    """Contracts at expiries outside `expiry_focus` are ignored."""
    contracts = [
        _contract(strike=110.0, option_type=OptionType.CALL, open_interest=1000, expiry=_EXPIRY),
        _contract(strike=110.0, option_type=OptionType.CALL, open_interest=99999, expiry=_FAR_EXPIRY),
    ]
    proxy = compute_dealer_gamma_proxy(
        contracts=contracts, spot=100.0, expiry_focus=[_EXPIRY]
    )
    # Only the EXPIRY contribution should count: -1 · 1000 · 10 = -10000.
    assert proxy == pytest.approx(-10000.0)


def test_dealer_gamma_multiple_expiries_in_focus() -> None:
    """`expiry_focus` may include multiple expiries; all contribute."""
    contracts = [
        _contract(strike=110.0, option_type=OptionType.CALL, open_interest=1000, expiry=_EXPIRY),
        _contract(strike=110.0, option_type=OptionType.CALL, open_interest=2000, expiry=_FAR_EXPIRY),
    ]
    proxy = compute_dealer_gamma_proxy(
        contracts=contracts, spot=100.0, expiry_focus=[_EXPIRY, _FAR_EXPIRY]
    )
    # -1 · 1000 · 10 + -1 · 2000 · 10 = -30000
    assert proxy == pytest.approx(-30000.0)


# ----------------------------------------------------------------------
# input validation
# ----------------------------------------------------------------------


def test_dealer_gamma_zero_spot_raises() -> None:
    contracts = [
        _contract(strike=100.0, option_type=OptionType.CALL, open_interest=1000)
    ]
    with pytest.raises(ValueError, match="spot must be > 0"):
        compute_dealer_gamma_proxy(
            contracts=contracts, spot=0.0, expiry_focus=[_EXPIRY]
        )


def test_dealer_gamma_negative_spot_raises() -> None:
    contracts = [
        _contract(strike=100.0, option_type=OptionType.CALL, open_interest=1000)
    ]
    with pytest.raises(ValueError, match="spot must be > 0"):
        compute_dealer_gamma_proxy(
            contracts=contracts, spot=-1.0, expiry_focus=[_EXPIRY]
        )


def test_dealer_gamma_empty_focus_raises() -> None:
    contracts = [
        _contract(strike=100.0, option_type=OptionType.CALL, open_interest=1000)
    ]
    with pytest.raises(ValueError, match="expiry_focus must contain"):
        compute_dealer_gamma_proxy(
            contracts=contracts, spot=100.0, expiry_focus=[]
        )


def test_dealer_gamma_no_contracts_at_focus_raises() -> None:
    contracts = [
        _contract(strike=100.0, option_type=OptionType.CALL, open_interest=1000, expiry=_FAR_EXPIRY)
    ]
    with pytest.raises(ValueError, match="no contracts present"):
        compute_dealer_gamma_proxy(
            contracts=contracts, spot=100.0, expiry_focus=[_EXPIRY]
        )


# ----------------------------------------------------------------------
# property tests
# ----------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(
    contracts_data=st.lists(
        st.tuples(
            st.floats(min_value=1.0, max_value=1000.0, allow_nan=False),
            st.sampled_from([OptionType.CALL, OptionType.PUT]),
            st.integers(min_value=0, max_value=100_000),
        ),
        min_size=1,
        max_size=30,
    ),
    spot=st.floats(min_value=1.0, max_value=1000.0, allow_nan=False),
)
def test_dealer_gamma_finite_and_signed_correctly(
    contracts_data: list[tuple[float, OptionType, int]],
    spot: float,
) -> None:
    """For any valid input, the proxy is finite and matches the sign rule."""
    contracts = [
        _contract(strike=k, option_type=ot, open_interest=oi)
        for (k, ot, oi) in contracts_data
    ]
    proxy = compute_dealer_gamma_proxy(
        contracts=contracts, spot=spot, expiry_focus=[_EXPIRY]
    )
    # Sanity: finite.
    assert proxy == proxy  # not NaN
    # Re-derive the sign by exhaustive enumeration and verify.
    expected = 0.0
    for k, ot, oi in contracts_data:
        sign = -1 if ot is OptionType.CALL else +1
        expected += sign * oi * (k - spot)
    assert proxy == pytest.approx(expected)


@given(
    multiplier=st.integers(min_value=1, max_value=100),
)
def test_dealer_gamma_linear_in_oi(multiplier: int) -> None:
    """The proxy is linear in OI: multiplying all OIs by k multiplies proxy by k."""
    base = [
        _contract(strike=110.0, option_type=OptionType.CALL, open_interest=1000),
        _contract(strike=90.0, option_type=OptionType.PUT, open_interest=500),
        _contract(strike=120.0, option_type=OptionType.CALL, open_interest=300),
    ]
    scaled = [
        _contract(
            strike=c.strike,
            option_type=c.option_type,
            open_interest=c.open_interest * multiplier,
        )
        for c in base
    ]
    base_proxy = compute_dealer_gamma_proxy(
        contracts=base, spot=100.0, expiry_focus=[_EXPIRY]
    )
    scaled_proxy = compute_dealer_gamma_proxy(
        contracts=scaled, spot=100.0, expiry_focus=[_EXPIRY]
    )
    assert scaled_proxy == pytest.approx(base_proxy * multiplier)
