"""Trend-strength (Wilder ADX) primitive tests (M1.3)."""

from __future__ import annotations

import math
import random

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from engine.market_state import compute_trend_strength, wilder_adx
from engine.market_state.trend_strength import DEFAULT_LOOKBACK

# ----------------------------------------------------------------------
# wilder_adx — hand-computed reference + edge cases
# ----------------------------------------------------------------------


def test_wilder_adx_monotonic_uptrend_lookback_2() -> None:
    """Hand-computed reference: monotonic uptrend with constant +$1/bar.

    Bars: (10,9,9.5), (11,10,10.5), (12,11,11.5), (13,12,12.5), (14,13,13.5)

    Each bar (i ≥ 1):
      TR = max(1, |hi - prev_close|, |lo - prev_close|) = 1.5
      up_move = +1, down_move = -1 → +DM = 1, -DM = 0

    With n=2 RMA: rma_tr = [1.5, 1.5, 1.5, 1.5], rma_+dm = [1,1,1,1], rma_-dm = [0,0,0,0]
    +DI = 100·1/1.5 ≈ 66.67, -DI = 0 → DX = 100 (every period).
    ADX = 100.
    """
    high = [10.0, 11.0, 12.0, 13.0, 14.0]
    low = [9.0, 10.0, 11.0, 12.0, 13.0]
    close = [9.5, 10.5, 11.5, 12.5, 13.5]
    adx = wilder_adx(high=high, low=low, close=close, lookback=2)
    assert adx == pytest.approx(100.0, abs=1e-9)


def test_wilder_adx_flat_market_zero() -> None:
    """Flat OHLC (TR = 0 everywhere) → ADX = 0 (no directional movement)."""
    n = 5
    high = [100.0] * (2 * n + 1)
    low = [100.0] * (2 * n + 1)
    close = [100.0] * (2 * n + 1)
    assert wilder_adx(high=high, low=low, close=close, lookback=n) == 0.0


def test_wilder_adx_monotonic_downtrend_high() -> None:
    """Monotonic downtrend should produce a high ADX (sign-agnostic)."""
    high = [110.0 - i for i in range(40)]
    low = [109.0 - i for i in range(40)]
    close = [109.5 - i for i in range(40)]
    adx = wilder_adx(high=high, low=low, close=close, lookback=14)
    assert adx > 30.0  # any sustained directional move yields high ADX


# ----------------------------------------------------------------------
# wilder_adx — edge cases
# ----------------------------------------------------------------------


def test_wilder_adx_insufficient_bars_raises() -> None:
    """`< 2 * lookback + 1` bars → ValueError."""
    n = 14
    high = [100.0] * (2 * n)  # exactly one short
    low = [99.0] * (2 * n)
    close = [99.5] * (2 * n)
    with pytest.raises(ValueError, match="requires"):
        wilder_adx(high=high, low=low, close=close, lookback=n)


def test_wilder_adx_misaligned_arrays_raises() -> None:
    with pytest.raises(ValueError, match="identical length"):
        wilder_adx(high=[1.0] * 30, low=[1.0] * 30, close=[1.0] * 29, lookback=14)


def test_wilder_adx_lookback_below_two_raises() -> None:
    high = [1.0] * 30
    with pytest.raises(ValueError, match="lookback"):
        wilder_adx(high=high, low=high, close=high, lookback=1)


# ----------------------------------------------------------------------
# compute_trend_strength — normalization
# ----------------------------------------------------------------------


def test_trend_strength_strong_uptrend_returns_1() -> None:
    """Monotonic uptrend → ADX >> 40 → trend_strength = 1.0."""
    high = [100.0 + i for i in range(50)]
    low = [99.0 + i for i in range(50)]
    close = [99.5 + i for i in range(50)]
    assert compute_trend_strength(high=high, low=low, close=close) == 1.0


def test_trend_strength_flat_market_returns_0() -> None:
    """Flat market → ADX = 0 → clip01((0-20)/20) = 0.0."""
    high = [100.0] * 50
    low = [100.0] * 50
    close = [100.0] * 50
    assert compute_trend_strength(high=high, low=low, close=close) == 0.0


def test_trend_strength_insufficient_history_returns_neutral_half() -> None:
    """Below `2 * n + 10` bars → 0.5 sentinel (NOT a raise — see §22.5)."""
    n = 14
    short_history = 2 * n + 9  # one short of threshold
    high = [100.0 + i for i in range(short_history)]
    low = [99.0 + i for i in range(short_history)]
    close = [99.5 + i for i in range(short_history)]
    assert compute_trend_strength(high=high, low=low, close=close) == 0.5


def test_trend_strength_at_threshold_engages_real_adx() -> None:
    """Exactly `2 * n + 10` bars → real ADX path, not 0.5 sentinel.

    With a strong uptrend at the threshold, we expect the real ADX path
    to yield a value > 0.5 (a strong-trend signal). The point of this
    test is to confirm the threshold gate is exclusive (< not <=).
    """
    n = 14
    threshold_history = 2 * n + 10
    high = [100.0 + i for i in range(threshold_history)]
    low = [99.0 + i for i in range(threshold_history)]
    close = [99.5 + i for i in range(threshold_history)]
    result = compute_trend_strength(high=high, low=low, close=close)
    assert result > 0.5  # real strong-trend signal, not the neutral fallback
    assert result <= 1.0


def test_trend_strength_misaligned_arrays_raises() -> None:
    with pytest.raises(ValueError, match="identical length"):
        compute_trend_strength(high=[1.0] * 50, low=[1.0] * 50, close=[1.0] * 49)


def test_trend_strength_lookback_below_two_raises() -> None:
    with pytest.raises(ValueError, match="lookback"):
        compute_trend_strength(
            high=[1.0] * 50, low=[1.0] * 50, close=[1.0] * 50, lookback=1
        )


def test_trend_strength_default_lookback_is_14() -> None:
    """Sanity check on the constant — Wilder's original convention."""
    assert DEFAULT_LOOKBACK == 14


# ----------------------------------------------------------------------
# compute_trend_strength — properties (hypothesis)
# ----------------------------------------------------------------------


@given(
    seed=st.integers(min_value=0, max_value=10_000),
    n_bars=st.integers(min_value=50, max_value=200),
)
@settings(deadline=None, max_examples=30)
def test_trend_strength_always_in_unit_interval(seed: int, n_bars: int) -> None:
    """For random walks, trend_strength stays in [0, 1] regardless of input."""
    rng = random.Random(seed)
    close: list[float] = [100.0]
    for _ in range(n_bars - 1):
        close.append(max(0.01, close[-1] + rng.uniform(-2.0, 2.0)))
    high = [c + abs(rng.uniform(0.0, 1.0)) for c in close]
    low = [max(0.01, c - abs(rng.uniform(0.0, 1.0))) for c in close]
    result = compute_trend_strength(high=high, low=low, close=close)
    assert 0.0 <= result <= 1.0
    assert math.isfinite(result)


def test_trend_strength_random_walk_lower_than_uptrend() -> None:
    """A noisy series (no persistent direction) should score lower than a clean trend."""
    rng = random.Random(42)
    n = 100
    walk_close = [100.0]
    for _ in range(n - 1):
        walk_close.append(max(0.01, walk_close[-1] + rng.gauss(0.0, 1.0)))
    walk_high = [c + 0.5 for c in walk_close]
    walk_low = [c - 0.5 for c in walk_close]

    trend_close = [100.0 + 0.5 * i for i in range(n)]
    trend_high = [c + 0.5 for c in trend_close]
    trend_low = [c - 0.5 for c in trend_close]

    walk_score = compute_trend_strength(high=walk_high, low=walk_low, close=walk_close)
    trend_score = compute_trend_strength(
        high=trend_high, low=trend_low, close=trend_close
    )
    assert trend_score > walk_score
