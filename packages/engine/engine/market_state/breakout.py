"""Breakout-signal primitive.

Per plan v1.2 §22.5 (canonical formula) and §17 M1.3.

The breakout signal is one of the canonical inputs to the M1.4 Market
State Engine `classify()` — specifically the `breakout_signal` field of
the §22.3 extended signature. It feeds the BREAKOUT regime branch and
informs the §22.8 `reduce_coverage_on_breakout_post_event` rule.

A breakout has four signatures, each contributing to the [0, 1] score:

  move_signal   |Δspot| over a 5-day window, normalized by 5%.
                A 5%+ move is the upper bound (signal = 1).
  vol_signal    +ΔIV over the same window, normalized by 10%.
                Negative IV change does NOT count as a breakout signal
                (a vol crush during a breakout is information about IV,
                not about price action) — clipped to [0, 1] from below.
  oi_signal     |OI shift ratio|, normalized by 1.0.
                A 100%+ OI rotation is the upper bound. Sign-agnostic
                (OI shifting either direction signals positioning change).
  break_signal  Distance above resistance, normalized by 2%, gated on
                `above_resistance`. Returns 0.0 when not above the
                resistance level — there's no "breakout" without
                actually breaking through.

The four signals are weight-blended:

  signal = 0.35·move + 0.20·vol + 0.20·oi + 0.25·break
         = clip01(weighted sum)

Per §22.5 the weights sum to 1.0 — the result is always in [0, 1]
regardless of clipping (each term is independently in [0, 1]).

Pure function (per ADR-0005). Edge cases (non-positive prices) raise
`ValueError` rather than returning a sentinel — the inputs to the
breakout signal are derived metrics from data ingestion, not raw market
data, so non-positive values represent a programmer error upstream.
"""

from __future__ import annotations

from engine._utils import clip01

# Calibration thresholds. Each anchors a "max signal = 1.0" point.
# Plan v1.2 §22.5 fixes these magic numbers as part of the formula spec.
_MOVE_SIGNAL_THRESHOLD = 0.05  # 5% move over the 5d window
_VOL_SIGNAL_THRESHOLD = 0.10   # 10% absolute IV change
_BREAK_SIGNAL_THRESHOLD = 0.02  # 2% above resistance

# Weights — must sum to 1.0 so the composite stays bounded by [0, 1].
_W_MOVE = 0.35
_W_VOL = 0.20
_W_OI = 0.20
_W_BREAK = 0.25


def compute_breakout_signal(
    *,
    spot: float,
    spot_5d_ago: float,
    atm_iv_change_5d: float,
    oi_shift_ratio: float,
    above_resistance: bool,
    above_resistance_pct: float,
) -> float:
    """Composite breakout signal in [0, 1] per plan v1.2 §22.5.

    Args:
        spot: Current spot. Must be > 0.
        spot_5d_ago: Spot 5 trading days ago. Must be > 0.
        atm_iv_change_5d: ATM IV change over the 5d window, decimal.
                          Positive values count toward breakout; negative
                          values clip to 0 (IV crush during breakout is
                          a vol signal, not a price-action signal).
        oi_shift_ratio: Open-interest rotation magnitude. Sign-agnostic
                        (`abs()` applied internally). 1.0 = full rotation.
        above_resistance: Whether spot is above the relevant resistance
                          level. The break_signal is gated on this.
        above_resistance_pct: Distance above resistance as a fraction.
                              Only counted when `above_resistance` is
                              True. Negative values when `above_resistance`
                              is True are clipped to 0 (caller error
                              tolerance).

    Returns:
        Composite score in [0, 1]. Higher = stronger breakout signal.

    Raises:
        ValueError: `spot` or `spot_5d_ago` is non-positive.
    """
    if spot <= 0:
        raise ValueError(f"compute_breakout_signal: spot must be > 0; got {spot}")
    if spot_5d_ago <= 0:
        raise ValueError(
            f"compute_breakout_signal: spot_5d_ago must be > 0; got {spot_5d_ago}"
        )

    pct_move = (spot - spot_5d_ago) / spot_5d_ago
    move_signal = clip01(abs(pct_move) / _MOVE_SIGNAL_THRESHOLD)
    vol_signal = clip01(atm_iv_change_5d / _VOL_SIGNAL_THRESHOLD)
    oi_signal = clip01(abs(oi_shift_ratio))
    break_signal = (
        clip01(above_resistance_pct / _BREAK_SIGNAL_THRESHOLD)
        if above_resistance
        else 0.0
    )

    composite = (
        _W_MOVE * move_signal
        + _W_VOL * vol_signal
        + _W_OI * oi_signal
        + _W_BREAK * break_signal
    )
    return clip01(composite)
