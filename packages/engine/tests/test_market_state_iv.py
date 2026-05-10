"""IV rank + IV percentile tests (M1.1)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from engine.market_state import iv_percentile, iv_rank
from engine.market_state.iv import MIN_IV_HISTORY

# ----------------------------------------------------------------------
# iv_rank
# ----------------------------------------------------------------------


def _ascending_history(start: float, step: float, n: int = 30) -> list[float]:
    return [start + step * i for i in range(n)]


def test_iv_rank_at_max() -> None:
    """Current IV at the historical maximum → rank = 1.0."""
    history = _ascending_history(0.10, 0.01, 30)  # 0.10 .. 0.39
    assert iv_rank(current_iv=0.39, history=history) == pytest.approx(1.0, abs=1e-12)


def test_iv_rank_at_min() -> None:
    """Current IV at the historical minimum → rank = 0.0."""
    history = _ascending_history(0.10, 0.01, 30)  # 0.10 .. 0.39
    assert iv_rank(current_iv=0.10, history=history) == pytest.approx(0.0, abs=1e-12)


def test_iv_rank_at_midpoint() -> None:
    """Halfway between min and max → rank = 0.5."""
    history = _ascending_history(0.20, 0.01, 30)  # 0.20 .. 0.49
    midpoint = (0.20 + 0.49) / 2.0  # 0.345
    assert iv_rank(current_iv=midpoint, history=history) == pytest.approx(0.5, abs=1e-9)


def test_iv_rank_clips_above_max() -> None:
    """Out-of-range above max → clipped to 1.0 (no panic)."""
    history = _ascending_history(0.20, 0.01, 30)
    assert iv_rank(current_iv=10.0, history=history) == 1.0


def test_iv_rank_clips_below_min() -> None:
    """Out-of-range below min → clipped to 0.0 (no panic)."""
    history = _ascending_history(0.20, 0.01, 30)
    assert iv_rank(current_iv=-0.5, history=history) == 0.0


def test_iv_rank_constant_history_returns_half() -> None:
    """Degenerate case: max == min → return 0.5 (the 'no information' prior)."""
    assert iv_rank(current_iv=0.30, history=[0.30] * 30) == 0.5
    # Even when current is far from the constant — the function can't say more.
    assert iv_rank(current_iv=0.99, history=[0.30] * 30) == 0.5


def test_iv_rank_short_history_raises() -> None:
    with pytest.raises(ValueError, match=f">= {MIN_IV_HISTORY}"):
        iv_rank(current_iv=0.30, history=[0.30] * (MIN_IV_HISTORY - 1))


def test_iv_rank_at_threshold_succeeds() -> None:
    """Exactly MIN_IV_HISTORY (= 30) observations is enough."""
    history = _ascending_history(0.10, 0.01, MIN_IV_HISTORY)
    # Should not raise.
    iv_rank(current_iv=0.20, history=history)


@given(
    history=st.lists(
        st.floats(min_value=0.01, max_value=2.0, allow_nan=False, allow_infinity=False),
        min_size=30,
        max_size=500,
    ),
    current_iv=st.floats(
        min_value=-1.0, max_value=10.0, allow_nan=False, allow_infinity=False
    ),
)
def test_iv_rank_always_in_unit_interval(
    history: list[float], current_iv: float
) -> None:
    result = iv_rank(current_iv=current_iv, history=history)
    assert 0.0 <= result <= 1.0


# ----------------------------------------------------------------------
# iv_percentile
# ----------------------------------------------------------------------


def test_iv_percentile_above_all() -> None:
    """Current IV above every observation → percentile = 1.0."""
    history = _ascending_history(0.20, 0.01, 30)  # 0.20 .. 0.49
    assert iv_percentile(current_iv=0.99, history=history) == 1.0


def test_iv_percentile_below_all() -> None:
    """Current IV below every observation → percentile = 0.0."""
    history = _ascending_history(0.20, 0.01, 30)
    assert iv_percentile(current_iv=0.05, history=history) == 0.0


def test_iv_percentile_at_median() -> None:
    """30 unique values; current = 16th element → 15 of 30 are strictly below = 0.5."""
    history = _ascending_history(0.20, 0.01, 30)  # sorted, unique
    median_value = history[15]
    assert iv_percentile(current_iv=median_value, history=history) == pytest.approx(
        0.5, abs=1e-12
    )


def test_iv_percentile_ties_not_counted() -> None:
    """Repeated value: current matches all → percentile = 0.0 (none strictly below)."""
    history = [0.30] * 30
    assert iv_percentile(current_iv=0.30, history=history) == 0.0


def test_iv_percentile_short_history_raises() -> None:
    with pytest.raises(ValueError, match=f">= {MIN_IV_HISTORY}"):
        iv_percentile(current_iv=0.30, history=[0.30] * (MIN_IV_HISTORY - 1))


@given(
    history=st.lists(
        st.floats(min_value=0.01, max_value=2.0, allow_nan=False, allow_infinity=False),
        min_size=30,
        max_size=500,
    ),
    current_iv=st.floats(
        min_value=-1.0, max_value=10.0, allow_nan=False, allow_infinity=False
    ),
)
def test_iv_percentile_always_in_unit_interval(
    history: list[float], current_iv: float
) -> None:
    result = iv_percentile(current_iv=current_iv, history=history)
    assert 0.0 <= result <= 1.0
