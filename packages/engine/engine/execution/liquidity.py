"""Liquidity scoring primitives for the Execution Feasibility Module.

Per plan v1.2 §9.8.

The §9.8 formula:

    liquidity = clip01(
        0.4 × norm_oi(oi)
      + 0.4 × norm_volume(volume)
      + 0.2 × (1 − min(spread_bps, 300) / 300)
    )

Three single-question pure functions feed it:

  - `norm_oi(oi)` — open interest normalizer
  - `norm_volume(volume)` — daily volume normalizer
  - `compute_spread_bps(bid, ask, mid)` — spread in basis points of mid

The V1 saturation constants are absolute (1,000 OI saturates; 200
volume saturates) rather than chain-relative. That keeps the math
chain-independent — useful for unit tests and for inputs that don't
carry the full `ChainSnapshot`. Phase 4 ML may learn a chain-relative
normalizer; the per-component contract (returns [0, 1]) is the
replaceable-node boundary.
"""

from __future__ import annotations

from engine._utils import clip01

# Saturation thresholds — chosen for V1 MSFT chain liquidity.
# A weekly MSFT option strike with OI ≥ 1,000 is "decently liquid";
# at this point the OI signal is fully captured by the [0, 1] score.
_OI_FULL_SATURATION: float = 1000.0

# Daily volume ≥ 200 contracts is similarly "decently liquid" for
# strikes the engine cares about. Front-month ATM trades much more;
# back-month OTM trades much less.
_VOLUME_FULL_SATURATION: float = 200.0

# Per §9.8 the spread component cuts off at 300 bps (3%).
# Spreads ≥ 300 bps contribute 0 to liquidity.
_SPREAD_CAP_BPS: int = 300

# Minimum mid-price floor for the bps calculation. Floors at $0.01
# to avoid division by zero on a broken quote (mid == 0).
_MIN_MID_FLOOR: float = 0.01

# Sentinel spread for invalid quotes (missing or inverted bid/ask).
# Chosen large enough to drive liquidity and fill_confidence to 0
# even after clipping, but bounded so callers can store it as an int.
_INVALID_SPREAD_BPS: int = 9999

# §9.8 component weights — locked V1 priors.
_W_OI: float = 0.4
_W_VOLUME: float = 0.4
_W_SPREAD: float = 0.2


def norm_oi(oi: int) -> float:
    """Open-interest normalizer; linear ramp to `_OI_FULL_SATURATION` = 1.0.

    V1 calibration:
      - `oi ≤ 0`           → 0.0
      - `oi ∈ [0, 1000]`   → `oi / 1000`
      - `oi ≥ 1000`        → 1.0

    Linear is a deliberate simplification — real OI distributions are
    log-normal, and a log-saturation is easy to motivate for liquid
    underlyings like SPY (median OI ≫ 1000). For MSFT (median OI in
    the hundreds for weekly OTM) linear at 1000 is a reasonable V1.

    Returns `[0, 1]`.
    """
    if oi <= 0:
        return 0.0
    return clip01(oi / _OI_FULL_SATURATION)


def norm_volume(volume: int) -> float:
    """Daily-volume normalizer; linear ramp to `_VOLUME_FULL_SATURATION` = 1.0.

    V1 calibration:
      - `volume ≤ 0`         → 0.0
      - `volume ∈ [0, 200]`  → `volume / 200`
      - `volume ≥ 200`       → 1.0

    Returns `[0, 1]`.
    """
    if volume <= 0:
        return 0.0
    return clip01(volume / _VOLUME_FULL_SATURATION)


def compute_spread_bps(
    *,
    bid: float | None,
    ask: float | None,
    mid: float | None = None,
) -> int:
    """Bid-ask spread in basis points of mid.

    `spread_bps = round((ask − bid) / max(mid, $0.01) × 10000)`

    When `mid` is not supplied, falls back to `(bid + ask) / 2`.

    Returns `_INVALID_SPREAD_BPS` (9999) when either side of the quote
    is missing or the spread is non-positive (broken / crossed market).
    Liquidity / fill calculations downstream clip these sentinels to 0.

    Returns an integer (rounded) in `[0, 9999]`.
    """
    if bid is None or ask is None or ask <= bid:
        return _INVALID_SPREAD_BPS
    spread_dollars = ask - bid
    effective_mid = mid if mid is not None else (bid + ask) / 2.0
    effective_mid = max(effective_mid, _MIN_MID_FLOOR)
    bps = int(round((spread_dollars / effective_mid) * 10000.0))
    # Cap to the sentinel ceiling so callers can store as a bounded int.
    return min(max(bps, 0), _INVALID_SPREAD_BPS)


def liquidity_score(
    *,
    oi: int,
    volume: int,
    spread_bps: int,
) -> float:
    """Per-leg liquidity score per plan §9.8.

    Formula:
        clip01(0.4 × norm_oi(oi)
             + 0.4 × norm_volume(volume)
             + 0.2 × (1 − min(spread_bps, 300) / 300))

    Returns `[0, 1]`.
    """
    spread_component = 1.0 - min(spread_bps, _SPREAD_CAP_BPS) / float(_SPREAD_CAP_BPS)
    return clip01(
        _W_OI * norm_oi(oi)
        + _W_VOLUME * norm_volume(volume)
        + _W_SPREAD * spread_component
    )
