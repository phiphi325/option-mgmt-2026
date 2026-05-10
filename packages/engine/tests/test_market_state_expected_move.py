"""Expected-move primitive tests (M1.2)."""

from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from engine.market_state import expected_move, expected_move_pct
from engine.market_state.hv import TRADING_DAYS_PER_YEAR

# ----------------------------------------------------------------------
# happy paths
# ----------------------------------------------------------------------


def test_expected_move_known_value_30_dte() -> None:
    """spot=100, IV=0.20, dte=30 → 100 * 0.20 * sqrt(30/252) ≈ 6.901."""
    em = expected_move(spot=100.0, atm_iv=0.20, dte_days=30)
    expected = 100.0 * 0.20 * math.sqrt(30 / 252)
    assert em == pytest.approx(expected, rel=1e-12)
    assert em == pytest.approx(6.901, abs=0.01)


def test_expected_move_known_value_252_dte() -> None:
    """At DTE = 252 (one year) the move equals spot * iv."""
    em = expected_move(spot=400.0, atm_iv=0.30, dte_days=252)
    assert em == pytest.approx(400.0 * 0.30, rel=1e-12)


def test_expected_move_zero_dte_returns_zero() -> None:
    """Zero days = zero time = zero move."""
    assert expected_move(spot=100.0, atm_iv=0.50, dte_days=0) == 0.0


def test_expected_move_zero_iv_returns_zero() -> None:
    """Zero vol = zero move."""
    assert expected_move(spot=100.0, atm_iv=0.0, dte_days=30) == 0.0


def test_expected_move_pct_no_spot_factor() -> None:
    """expected_move_pct(iv, dte) * spot == expected_move(spot, iv, dte)."""
    spot = 415.0
    iv = 0.28
    dte = 21
    pct = expected_move_pct(atm_iv=iv, dte_days=dte)
    dollars = expected_move(spot=spot, atm_iv=iv, dte_days=dte)
    assert pct * spot == pytest.approx(dollars, rel=1e-12)


def test_expected_move_scales_linearly_in_spot() -> None:
    em_at_100 = expected_move(spot=100.0, atm_iv=0.30, dte_days=30)
    em_at_400 = expected_move(spot=400.0, atm_iv=0.30, dte_days=30)
    assert em_at_400 == pytest.approx(4.0 * em_at_100, rel=1e-12)


def test_expected_move_scales_linearly_in_iv() -> None:
    em_iv20 = expected_move(spot=100.0, atm_iv=0.20, dte_days=30)
    em_iv40 = expected_move(spot=100.0, atm_iv=0.40, dte_days=30)
    assert em_iv40 == pytest.approx(2.0 * em_iv20, rel=1e-12)


def test_expected_move_scales_with_sqrt_of_dte() -> None:
    """Move at 4× DTE is 2× the move at base DTE (sqrt time)."""
    em_30 = expected_move(spot=100.0, atm_iv=0.30, dte_days=30)
    em_120 = expected_move(spot=100.0, atm_iv=0.30, dte_days=120)
    assert em_120 == pytest.approx(2.0 * em_30, rel=1e-12)


# ----------------------------------------------------------------------
# edge cases
# ----------------------------------------------------------------------


def test_expected_move_negative_spot_raises() -> None:
    with pytest.raises(ValueError, match="spot"):
        expected_move(spot=-100.0, atm_iv=0.20, dte_days=30)


def test_expected_move_zero_spot_raises() -> None:
    with pytest.raises(ValueError, match="spot"):
        expected_move(spot=0.0, atm_iv=0.20, dte_days=30)


def test_expected_move_negative_iv_raises() -> None:
    with pytest.raises(ValueError, match="atm_iv"):
        expected_move(spot=100.0, atm_iv=-0.01, dte_days=30)


def test_expected_move_negative_dte_raises() -> None:
    with pytest.raises(ValueError, match="dte_days"):
        expected_move(spot=100.0, atm_iv=0.20, dte_days=-1)


def test_expected_move_pct_negative_iv_raises() -> None:
    with pytest.raises(ValueError, match="atm_iv"):
        expected_move_pct(atm_iv=-0.01, dte_days=30)


def test_expected_move_pct_negative_dte_raises() -> None:
    with pytest.raises(ValueError, match="dte_days"):
        expected_move_pct(atm_iv=0.20, dte_days=-1)


# ----------------------------------------------------------------------
# constants + properties
# ----------------------------------------------------------------------


def test_uses_252_trading_days() -> None:
    """Sanity check: the annualization factor matches the engine-wide constant."""
    em = expected_move(spot=100.0, atm_iv=1.0, dte_days=TRADING_DAYS_PER_YEAR)
    # At dte = 252, multiplier = sqrt(252/252) = 1.0, so em = spot * iv.
    assert em == pytest.approx(100.0, rel=1e-12)


@given(
    spot=st.floats(min_value=1.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
    atm_iv=st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False),
    dte_days=st.integers(min_value=0, max_value=3650),
)
def test_expected_move_always_non_negative(spot: float, atm_iv: float, dte_days: int) -> None:
    em = expected_move(spot=spot, atm_iv=atm_iv, dte_days=dte_days)
    assert em >= 0.0
    assert math.isfinite(em)


@given(
    atm_iv=st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False),
    dte_days=st.integers(min_value=0, max_value=3650),
)
def test_expected_move_pct_in_unit_interval_for_typical_inputs(
    atm_iv: float, dte_days: int
) -> None:
    """For dte_days <= 252 and iv <= 1.0, pct should be <= 1.0."""
    em_pct = expected_move_pct(atm_iv=atm_iv, dte_days=dte_days)
    assert em_pct >= 0.0
    assert math.isfinite(em_pct)
    if atm_iv <= 1.0 and dte_days <= TRADING_DAYS_PER_YEAR:
        assert em_pct <= 1.0
