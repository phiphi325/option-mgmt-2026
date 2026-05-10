"""Trend-strength primitive — Wilder ADX, normalized to [0, 1].

Per plan v1.2 §22.5 (Specifications for previously undefined functions)
and §17 M1.3.

The trend-strength scalar is one of the canonical inputs to the M1.4
Market State Engine `classify()` (§22.3 extended signature). It feeds
the LOW_IV_TREND vs LOW_IV_RANGE branch of the regime tree: high trend
strength + low IV → LOW_IV_TREND; low trend strength + low IV → range.

## Algorithm

J. Welles Wilder Jr.'s Average Directional Index (ADX), 1978. Standard
n=14 lookback. Implementation:

  1. For each bar i ≥ 1:
       TR[i]    = max(high[i] − low[i],
                      |high[i] − close[i−1]|,
                      |low[i]  − close[i−1]|)
       up_move  = high[i] − high[i−1]
       dn_move  = low[i−1] − low[i]
       +DM[i]   = up_move if up_move > dn_move and up_move > 0 else 0
       −DM[i]   = dn_move if dn_move > up_move and dn_move > 0 else 0

  2. Wilder RMA over each series with period n. Initial value is the
     simple mean of the first n raw values; subsequent values follow
     R[i] = (R[i−1] · (n−1) + raw[i]) / n.

  3. +DI = 100 · RMA(+DM) / RMA(TR)
     −DI = 100 · RMA(−DM) / RMA(TR)
     DX  = 100 · |+DI − −DI| / (+DI + −DI)

  4. ADX = Wilder RMA of DX (initial = mean of first n DX values).

Returns the most-recent ADX value (a float in roughly [0, 100]).

## Normalization

`compute_trend_strength` maps ADX to [0, 1]:

      ADX ≤ 20 → 0.0   (no meaningful trend)
      ADX = 30 → 0.5
      ADX ≥ 40 → 1.0   (strong trend)
      linear between, clipped at endpoints.

The 20 / 40 thresholds match common trader convention (Wilder's own
guidance + standard ADX interpretation).

## Insufficient history

Wilder ADX requires roughly `2n` bars to stabilize: n bars to seed the
TR / DM smoothers, plus n more to seed the DX smoother that becomes
ADX. Plan §22.5 demands `2n + 10` (n=14 → 38) to give a safety buffer
against noise dominating early ADX values. Below threshold,
`compute_trend_strength` returns **0.5** (the "no signal / neutral"
prior) — the M1.4 `classify()` keeps running rather than bailing.

`wilder_adx` itself raises `ValueError` below `2n + 1` (the
mathematical minimum). Use `compute_trend_strength` for the production
path; use `wilder_adx` only when callers want the raw indicator value
(e.g. diagnostic UI).
"""

from __future__ import annotations

from collections.abc import Sequence

from engine._utils import clip01

# Wilder's default period. Plan v1.2 §22.5 fixes n=14.
DEFAULT_LOOKBACK = 14

# Thresholds that define the [0, 1] trend-strength normalization band.
# ADX values at or below `_ADX_NO_TREND` map to 0.0; values at or above
# `_ADX_STRONG_TREND` map to 1.0; linear in between.
_ADX_NO_TREND = 20.0
_ADX_STRONG_TREND = 40.0


def _wilder_rma(values: Sequence[float], n: int) -> list[float]:
    """Wilder's running moving average. Returns a list of length len(values) − n + 1.

    Initial value is the simple mean of the first n raw values; each
    subsequent value is `(prev * (n - 1) + new) / n`.
    """
    initial = sum(values[:n]) / n
    out = [initial]
    for v in values[n:]:
        out.append((out[-1] * (n - 1) + v) / n)
    return out


def wilder_adx(
    *,
    high: Sequence[float],
    low: Sequence[float],
    close: Sequence[float],
    lookback: int = DEFAULT_LOOKBACK,
) -> float:
    """Most-recent Wilder ADX value over the supplied OHLC bars.

    Args:
        high: Period highs, ordered oldest → newest.
        low: Period lows, ordered oldest → newest. Must align with `high`.
        close: Period closes, ordered oldest → newest. Must align.
        lookback: Wilder period. Default 14 (Wilder's original).

    Returns:
        The latest ADX value (typically ~0..100 — not bounded above).

    Raises:
        ValueError: arrays misaligned, lookback < 2, or fewer than
                    `2 * lookback + 1` bars (the mathematical minimum
                    for ADX to be defined at all).
    """
    if not (len(high) == len(low) == len(close)):
        raise ValueError(
            f"wilder_adx: high/low/close arrays must have identical length; "
            f"got {len(high)}, {len(low)}, {len(close)}"
        )
    if lookback < 2:
        raise ValueError(f"wilder_adx: lookback must be >= 2; got {lookback}")
    n = lookback
    if len(close) < 2 * n + 1:
        raise ValueError(
            f"wilder_adx with lookback={n} requires >= {2 * n + 1} bars; "
            f"got {len(close)}"
        )

    # 1. Per-bar TR + directional movement, indexed against `close[i-1]`.
    tr: list[float] = []
    plus_dm: list[float] = []
    minus_dm: list[float] = []
    for i in range(1, len(close)):
        bar_tr = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1]),
        )
        up_move = high[i] - high[i - 1]
        dn_move = low[i - 1] - low[i]
        bar_plus = up_move if (up_move > dn_move and up_move > 0) else 0.0
        bar_minus = dn_move if (dn_move > up_move and dn_move > 0) else 0.0
        tr.append(bar_tr)
        plus_dm.append(bar_plus)
        minus_dm.append(bar_minus)

    # We have len(close)-1 raw values. Need >= n for the first RMA seed.
    rma_tr = _wilder_rma(tr, n)
    rma_plus = _wilder_rma(plus_dm, n)
    rma_minus = _wilder_rma(minus_dm, n)

    # 2. DX series — one entry per RMA value.
    dx_series: list[float] = []
    # rma_tr / rma_plus / rma_minus have identical length by construction
    # (all are _wilder_rma(<same-length seq>, n)). strict= would catch a
    # future regression but the equal-length invariant is established
    # locally above; explicit B905 silence.
    for atr, p, m in zip(rma_tr, rma_plus, rma_minus):  # noqa: B905
        if atr <= 0.0:
            # Flat market (no true range) — directional movement is undefined.
            dx_series.append(0.0)
            continue
        plus_di = 100.0 * p / atr
        minus_di = 100.0 * m / atr
        di_sum = plus_di + minus_di
        if di_sum <= 0.0:
            dx_series.append(0.0)
            continue
        dx_series.append(100.0 * abs(plus_di - minus_di) / di_sum)

    # 3. ADX = Wilder RMA of DX. Need at least n DX values.
    if len(dx_series) < n:
        raise ValueError(
            f"wilder_adx: not enough DX observations to seed ADX RMA "
            f"(need {n}, got {len(dx_series)})"
        )
    adx_series = _wilder_rma(dx_series, n)
    return adx_series[-1]


def compute_trend_strength(
    *,
    high: Sequence[float],
    low: Sequence[float],
    close: Sequence[float],
    lookback: int = DEFAULT_LOOKBACK,
) -> float:
    """Trend-strength scalar in [0, 1] from Wilder ADX.

    Returns 0.5 (the "no signal / neutral" prior) when history is below
    the `2 * lookback + 10` threshold required for stable ADX — this is
    a deliberate non-raising path so the M1.4 `classify()` keeps running
    against partial data. Above threshold, returns the normalized ADX:

        clip01((ADX − 20) / 20)

    Args:
        high, low, close: Period OHLC bars, ordered oldest → newest.
                          All arrays must align.
        lookback: Wilder period. Default 14.

    Returns:
        Float in [0, 1]. 0.5 sentinel when history is too short for
        stable ADX.

    Raises:
        ValueError: arrays misaligned or lookback < 2. (Insufficient
                    history is NOT raised — see above.)
    """
    if not (len(high) == len(low) == len(close)):
        raise ValueError(
            f"compute_trend_strength: high/low/close arrays must have "
            f"identical length; got {len(high)}, {len(low)}, {len(close)}"
        )
    if lookback < 2:
        raise ValueError(
            f"compute_trend_strength: lookback must be >= 2; got {lookback}"
        )
    if len(close) < 2 * lookback + 10:
        return 0.5
    adx = wilder_adx(high=high, low=low, close=close, lookback=lookback)
    return clip01((adx - _ADX_NO_TREND) / (_ADX_STRONG_TREND - _ADX_NO_TREND))
