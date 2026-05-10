"""Breakout-signal primitive tests (M1.3)."""

from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from engine.market_state import compute_breakout_signal

# ----------------------------------------------------------------------
# happy paths
# ----------------------------------------------------------------------


def test_breakout_signal_all_zero_inputs() -> None:
    """No move, no vol change, no OI shift, not above resistance → 0.0."""
    sig = compute_breakout_signal(
        spot=100.0,
        spot_5d_ago=100.0,
        atm_iv_change_5d=0.0,
        oi_shift_ratio=0.0,
        above_resistance=False,
        above_resistance_pct=0.0,
    )
    assert sig == 0.0


def test_breakout_signal_all_max_inputs() -> None:
    """Every component at or above threshold → composite = 1.0."""
    sig = compute_breakout_signal(
        spot=110.0,           # +10% over 5d (>5% threshold)
        spot_5d_ago=100.0,
        atm_iv_change_5d=0.20, # +20% IV (>10% threshold)
        oi_shift_ratio=2.0,    # 200% OI rotation (>100% threshold)
        above_resistance=True,
        above_resistance_pct=0.05,  # 5% above resistance (>2% threshold)
    )
    assert sig == pytest.approx(1.0, abs=1e-12)


def test_breakout_signal_only_move_at_max() -> None:
    """Only the price-move component active → 0.35 (the move weight)."""
    sig = compute_breakout_signal(
        spot=110.0,           # +10%
        spot_5d_ago=100.0,
        atm_iv_change_5d=0.0,
        oi_shift_ratio=0.0,
        above_resistance=False,
        above_resistance_pct=0.0,
    )
    assert sig == pytest.approx(0.35, abs=1e-12)


def test_breakout_signal_only_vol_at_max() -> None:
    """Only the vol-change component active → 0.20 (the vol weight)."""
    sig = compute_breakout_signal(
        spot=100.0,
        spot_5d_ago=100.0,
        atm_iv_change_5d=0.20,  # 200% of threshold → clipped to 1.0
        oi_shift_ratio=0.0,
        above_resistance=False,
        above_resistance_pct=0.0,
    )
    assert sig == pytest.approx(0.20, abs=1e-12)


def test_breakout_signal_only_oi_at_max() -> None:
    """Only the OI-shift component active → 0.20 (the OI weight)."""
    sig = compute_breakout_signal(
        spot=100.0,
        spot_5d_ago=100.0,
        atm_iv_change_5d=0.0,
        oi_shift_ratio=2.0,
        above_resistance=False,
        above_resistance_pct=0.0,
    )
    assert sig == pytest.approx(0.20, abs=1e-12)


def test_breakout_signal_only_break_at_max() -> None:
    """Only the resistance-break component active → 0.25 (the break weight)."""
    sig = compute_breakout_signal(
        spot=100.0,
        spot_5d_ago=100.0,
        atm_iv_change_5d=0.0,
        oi_shift_ratio=0.0,
        above_resistance=True,
        above_resistance_pct=0.05,  # 250% of threshold → clipped to 1.0
    )
    assert sig == pytest.approx(0.25, abs=1e-12)


def test_breakout_signal_weights_sum_to_one() -> None:
    """Sanity: 0.35 + 0.20 + 0.20 + 0.25 = 1.00 (each component test sums correctly)."""
    sigs = [
        compute_breakout_signal(
            spot=110.0,
            spot_5d_ago=100.0,
            atm_iv_change_5d=0.0,
            oi_shift_ratio=0.0,
            above_resistance=False,
            above_resistance_pct=0.0,
        ),  # move only: 0.35
        compute_breakout_signal(
            spot=100.0,
            spot_5d_ago=100.0,
            atm_iv_change_5d=0.20,
            oi_shift_ratio=0.0,
            above_resistance=False,
            above_resistance_pct=0.0,
        ),  # vol only: 0.20
        compute_breakout_signal(
            spot=100.0,
            spot_5d_ago=100.0,
            atm_iv_change_5d=0.0,
            oi_shift_ratio=2.0,
            above_resistance=False,
            above_resistance_pct=0.0,
        ),  # oi only: 0.20
        compute_breakout_signal(
            spot=100.0,
            spot_5d_ago=100.0,
            atm_iv_change_5d=0.0,
            oi_shift_ratio=0.0,
            above_resistance=True,
            above_resistance_pct=0.05,
        ),  # break only: 0.25
    ]
    assert sum(sigs) == pytest.approx(1.0, abs=1e-12)


# ----------------------------------------------------------------------
# component semantics
# ----------------------------------------------------------------------


def test_breakout_signal_move_is_sign_agnostic() -> None:
    """A 5%+ move *down* should produce the same move_signal as up — abs() applied."""
    sig_up = compute_breakout_signal(
        spot=110.0,
        spot_5d_ago=100.0,
        atm_iv_change_5d=0.0,
        oi_shift_ratio=0.0,
        above_resistance=False,
        above_resistance_pct=0.0,
    )
    sig_down = compute_breakout_signal(
        spot=90.0,
        spot_5d_ago=100.0,
        atm_iv_change_5d=0.0,
        oi_shift_ratio=0.0,
        above_resistance=False,
        above_resistance_pct=0.0,
    )
    assert sig_up == sig_down


def test_breakout_signal_vol_negative_clipped() -> None:
    """Negative IV change does NOT count as a breakout signal (clipped to 0)."""
    sig = compute_breakout_signal(
        spot=100.0,
        spot_5d_ago=100.0,
        atm_iv_change_5d=-0.20,  # IV crush, not breakout
        oi_shift_ratio=0.0,
        above_resistance=False,
        above_resistance_pct=0.0,
    )
    assert sig == 0.0


def test_breakout_signal_oi_is_sign_agnostic() -> None:
    """abs(oi_shift_ratio) — sign of rotation doesn't matter."""
    sig_pos = compute_breakout_signal(
        spot=100.0,
        spot_5d_ago=100.0,
        atm_iv_change_5d=0.0,
        oi_shift_ratio=2.0,
        above_resistance=False,
        above_resistance_pct=0.0,
    )
    sig_neg = compute_breakout_signal(
        spot=100.0,
        spot_5d_ago=100.0,
        atm_iv_change_5d=0.0,
        oi_shift_ratio=-2.0,
        above_resistance=False,
        above_resistance_pct=0.0,
    )
    assert sig_pos == sig_neg


def test_breakout_signal_break_gated_on_above_resistance() -> None:
    """`above_resistance=False` → break component is 0 regardless of pct."""
    sig = compute_breakout_signal(
        spot=100.0,
        spot_5d_ago=100.0,
        atm_iv_change_5d=0.0,
        oi_shift_ratio=0.0,
        above_resistance=False,
        above_resistance_pct=0.10,  # 10% — would be max, but gate is False
    )
    assert sig == 0.0


def test_breakout_signal_partial_credit_below_threshold() -> None:
    """A 2.5% move = half of 5% threshold → move_signal = 0.5 → contributes 0.175."""
    sig = compute_breakout_signal(
        spot=102.5,            # +2.5%
        spot_5d_ago=100.0,
        atm_iv_change_5d=0.0,
        oi_shift_ratio=0.0,
        above_resistance=False,
        above_resistance_pct=0.0,
    )
    assert sig == pytest.approx(0.5 * 0.35, abs=1e-12)


# ----------------------------------------------------------------------
# edge cases
# ----------------------------------------------------------------------


def test_breakout_signal_zero_spot_raises() -> None:
    with pytest.raises(ValueError, match="spot must be > 0"):
        compute_breakout_signal(
            spot=0.0,
            spot_5d_ago=100.0,
            atm_iv_change_5d=0.0,
            oi_shift_ratio=0.0,
            above_resistance=False,
            above_resistance_pct=0.0,
        )


def test_breakout_signal_negative_spot_raises() -> None:
    with pytest.raises(ValueError, match="spot must be > 0"):
        compute_breakout_signal(
            spot=-1.0,
            spot_5d_ago=100.0,
            atm_iv_change_5d=0.0,
            oi_shift_ratio=0.0,
            above_resistance=False,
            above_resistance_pct=0.0,
        )


def test_breakout_signal_zero_spot_5d_ago_raises() -> None:
    """Division by zero protection."""
    with pytest.raises(ValueError, match="spot_5d_ago"):
        compute_breakout_signal(
            spot=100.0,
            spot_5d_ago=0.0,
            atm_iv_change_5d=0.0,
            oi_shift_ratio=0.0,
            above_resistance=False,
            above_resistance_pct=0.0,
        )


# ----------------------------------------------------------------------
# property tests
# ----------------------------------------------------------------------


@given(
    spot=st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False),
    spot_5d_ago=st.floats(
        min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False
    ),
    iv_change=st.floats(min_value=-1.0, max_value=2.0, allow_nan=False, allow_infinity=False),
    oi_ratio=st.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False),
    above_resistance=st.booleans(),
    above_pct=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)
def test_breakout_signal_always_in_unit_interval(
    spot: float,
    spot_5d_ago: float,
    iv_change: float,
    oi_ratio: float,
    above_resistance: bool,
    above_pct: float,
) -> None:
    sig = compute_breakout_signal(
        spot=spot,
        spot_5d_ago=spot_5d_ago,
        atm_iv_change_5d=iv_change,
        oi_shift_ratio=oi_ratio,
        above_resistance=above_resistance,
        above_resistance_pct=above_pct,
    )
    assert 0.0 <= sig <= 1.0
    assert math.isfinite(sig)
