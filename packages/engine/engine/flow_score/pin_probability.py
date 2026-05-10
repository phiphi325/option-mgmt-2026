"""Pin-probability primitive.

Per plan v1.2 §9.3 step 7 / §9.3a `sigmoid_pin()`.

`sigmoid_pin` estimates the probability that spot pins at the max-pain
strike at the nearest monthly opex. The estimator is a multiplicative
blend of three factors, each in `[0, 1]`:

  dist_factor  How close spot is to max_pain, normalized by spot.
               Within 2% → 1.0; beyond 2% → linearly to 0 at 5%.
  opex_factor  How close opex is. Within 14 trading days → linearly to
               1; ≥ 14 → 0.
  oi_factor    The supplied `oi_concentration_at_max_pain ∈ [0, 1]`.

The multiplicative combination is deliberate: all three factors must be
present for a meaningful pin signal. A 2% distance with 30-day opex
and 10% OI concentration is **not** a pin — even though one factor is
elevated, the others kill the joint probability.

Result is in `[0, 1]`.

Edge cases:

  - `dte_to_nearest_opex is None` or `> 30` → returns 0.0 (no opex in
    the relevant horizon).
  - `spot <= 0` or `max_pain <= 0` → `ValueError`.
  - `oi_concentration_at_max_pain` outside `[0, 1]` → `ValueError`.

Pure function (per ADR-0005).
"""

from __future__ import annotations

from engine._utils import clip01

# Pin tolerance. dist_pct <= _PIN_TIGHT_PCT → dist_factor saturates at 1.0;
# dist_pct >= _PIN_LOOSE_PCT → 0.0; linear between. Plan §9.3 step 7 does
# not specify exact thresholds; these are V1 priors calibrated to "tight
# pins are within 2% of max-pain; pins dissolve past 5%."
_PIN_TIGHT_PCT = 0.02
_PIN_LOOSE_PCT = 0.05

# Opex horizon. dte <= 14 (3 weeks) maps linearly to opex_factor; beyond
# 14 the pin force is functionally zero.
_OPEX_HORIZON_DAYS = 14
_OPEX_FAR_DAYS = 30  # beyond this, pin_probability is identically 0


def sigmoid_pin(
    *,
    spot: float,
    max_pain: float,
    dte_to_nearest_opex: int | None,
    oi_concentration_at_max_pain: float,
) -> float:
    """Multiplicative pin-probability estimator in [0, 1].

    Args:
        spot: Current underlying spot. Must be > 0.
        max_pain: Max-pain strike. Must be > 0.
        dte_to_nearest_opex: Trading days to the nearest monthly opex,
                             or None if no opex sits in the horizon.
                             Negative → clamped to 0 defensively.
        oi_concentration_at_max_pain: Fraction of OI sitting at the
                                      max-pain strike, in [0, 1].

    Returns:
        `dist_factor · opex_factor · oi_factor`, in [0, 1].

    Raises:
        ValueError: spot <= 0, max_pain <= 0, or
                    oi_concentration_at_max_pain outside [0, 1].
    """
    if spot <= 0.0:
        raise ValueError(f"sigmoid_pin: spot must be > 0; got {spot}")
    if max_pain <= 0.0:
        raise ValueError(f"sigmoid_pin: max_pain must be > 0; got {max_pain}")
    if not 0.0 <= oi_concentration_at_max_pain <= 1.0:
        raise ValueError(
            f"sigmoid_pin: oi_concentration_at_max_pain must be in [0, 1]; "
            f"got {oi_concentration_at_max_pain}"
        )

    if dte_to_nearest_opex is None or dte_to_nearest_opex >= _OPEX_FAR_DAYS:
        return 0.0
    dte = max(dte_to_nearest_opex, 0)

    dist_pct = abs(spot - max_pain) / spot
    if dist_pct <= _PIN_TIGHT_PCT:
        dist_factor = 1.0
    elif dist_pct >= _PIN_LOOSE_PCT:
        dist_factor = 0.0
    else:
        dist_factor = (_PIN_LOOSE_PCT - dist_pct) / (_PIN_LOOSE_PCT - _PIN_TIGHT_PCT)

    opex_factor = clip01(1.0 - dte / _OPEX_HORIZON_DAYS)

    oi_factor = oi_concentration_at_max_pain

    return clip01(dist_factor * opex_factor * oi_factor)
