"""Historical volatility (HV) computation tests (M1.1)."""

from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from engine.market_state import compute_hv
from engine.market_state.hv import TRADING_DAYS_PER_YEAR

# ----------------------------------------------------------------------
# happy paths
# ----------------------------------------------------------------------


def test_compute_hv_constant_prices_returns_zero() -> None:
    """No realized motion → HV = 0.0 (the function reports it; doesn't filter)."""
    prices = [100.0] * 31
    assert compute_hv(prices=prices, lookback=30) == 0.0


def test_compute_hv_uniform_log_returns_returns_zero() -> None:
    """A series with identical log returns → sample std = 0 → HV = 0."""
    prices = [100.0 * (1.01**i) for i in range(31)]  # exactly +1%/day
    assert compute_hv(prices=prices, lookback=30) == pytest.approx(0.0, abs=1e-12)


def test_compute_hv_alternating_returns_positive() -> None:
    """Alternating ±1% returns produce a stable, positive HV."""
    prices = [100.0]
    for i in range(30):
        prices.append(prices[-1] * (1.01 if i % 2 == 0 else 1.0 / 1.01))
    hv = compute_hv(prices=prices, lookback=30)
    assert hv > 0.0
    # Each return has |log| ≈ ln(1.01) ≈ 0.00995. With ~equal +/− around a
    # near-zero mean, the daily std ≈ 0.00995, annualized ≈ 0.158.
    assert hv == pytest.approx(0.00995 * math.sqrt(TRADING_DAYS_PER_YEAR), abs=0.01)


def test_compute_hv_lookback_smaller_than_30() -> None:
    """HV_10 from 11+ prices: only the most-recent 11 prices are used."""
    # Mostly-flat, with a single bump in the OLD prefix outside the window.
    prices = [100.0] * 50 + [200.0] + [100.0] * 50  # 101 prices total
    hv_10 = compute_hv(prices=prices, lookback=10)
    # The bump at index 50 is outside the trailing 11 prices, so HV = 0.
    assert hv_10 == 0.0


def test_compute_hv_uses_most_recent_window_only() -> None:
    """Older prices outside (lookback + 1) don't affect HV."""
    # Volatile prefix; flat tail of 31 prices → HV computed on flat tail = 0.
    volatile_prefix = [50.0, 200.0] * 50  # 100 prices, very volatile
    flat_tail = [100.0] * 31
    prices = volatile_prefix + flat_tail
    assert compute_hv(prices=prices, lookback=30) == 0.0


# ----------------------------------------------------------------------
# edge cases
# ----------------------------------------------------------------------


def test_compute_hv_insufficient_prices_raises() -> None:
    """At least lookback + 1 prices are required."""
    with pytest.raises(ValueError, match="requires"):
        compute_hv(prices=[100.0] * 30, lookback=30)


def test_compute_hv_at_threshold_succeeds() -> None:
    """Exactly lookback + 1 prices is enough."""
    # Should not raise.
    assert compute_hv(prices=[100.0] * 31, lookback=30) == 0.0


def test_compute_hv_zero_price_raises() -> None:
    with pytest.raises(ValueError, match="positive"):
        compute_hv(prices=[100.0] * 30 + [0.0], lookback=30)


def test_compute_hv_negative_price_raises() -> None:
    with pytest.raises(ValueError, match="positive"):
        compute_hv(prices=[-1.0] + [100.0] * 30, lookback=30)


# ----------------------------------------------------------------------
# properties
# ----------------------------------------------------------------------


@given(
    prices=st.lists(
        st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        min_size=31,
        max_size=300,
    ),
)
def test_compute_hv_always_non_negative(prices: list[float]) -> None:
    hv = compute_hv(prices=prices, lookback=30)
    assert hv >= 0.0
    assert math.isfinite(hv)


@given(scale=st.floats(min_value=0.1, max_value=100.0, allow_nan=False, allow_infinity=False))
def test_compute_hv_scale_invariant(scale: float) -> None:
    """HV is scale-invariant: a uniform multiplicative re-scaling preserves it.

    This is a fundamental property of log-return-based vol — log(k*p2 / k*p1)
    = log(p2 / p1). If this fails, something is wrong with the calculation.
    """
    base_prices = [100.0 + i * 0.5 for i in range(31)]  # mild trend
    scaled = [p * scale for p in base_prices]
    base_hv = compute_hv(prices=base_prices, lookback=30)
    scaled_hv = compute_hv(prices=scaled, lookback=30)
    assert base_hv == pytest.approx(scaled_hv, abs=1e-10)
