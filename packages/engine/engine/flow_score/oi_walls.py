"""OI-walls computation.

Per plan v1.2 §9.3 step 1 and §17 M1.5.

An **OI wall** is a strike that has accumulated open interest far above the
chain median. Dealers hedging short gamma at high-OI strikes generate flow
that resists spot moves *through* the wall, making the strike a soft
support (highest large-OI strike strictly below spot) or resistance (lowest
large-OI strike strictly above spot).

`compute_oi_walls()` operates on the contracts in a `ChainSnapshot`,
filtered to the supplied focus expiries:

  1. Aggregate OI per strike across calls + puts in the focus expiries.
  2. Compute the threshold OI = `percentile_threshold` quantile of the
     per-strike OI distribution. Default threshold is 0.90 (top decile).
  3. Identify strikes whose OI exceeds the threshold.
  4. `support`     = max strictly-below-spot strike among qualifying strikes
                     (None if no qualifying strike sits below spot).
     `resistance`  = min strictly-above-spot strike among qualifying strikes
                     (None if no qualifying strike sits above spot).

Returns the canonical `engine.scoring.structure.OiWalls` dataclass with
`support`, `resistance`, `support_oi`, `resistance_oi`, and `total_oi`
populated. The wiring matrix (plan §9.11) names this module as the
*producer* of `OiWalls`; `engine.scoring.structure_score()` is the
consumer.

Pure function (per ADR-0005). No I/O.

Edge cases:

  - No contracts at the requested expiries → `ValueError`. OI walls are
    undefined without a chain to scan.
  - `percentile_threshold` outside `[0, 1)` → `ValueError`. The threshold
    has to leave at least one strike *above* the percentile, so a value
    of 1.0 is rejected (no strike can exceed the maximum).
  - All qualifying strikes sit above spot → `support` is `None`,
    `resistance` is set. Symmetric on the other side.
  - No qualifying strikes at all (e.g. flat OI distribution) → both
    `support` and `resistance` are `None`; `*_oi` fields are 0;
    `total_oi` still reflects the aggregate.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from engine.scoring.structure import OiWalls
from engine.types import OptionContract

# Plan v1.2 §9.3: 90th percentile is the V1 OI-wall threshold. A strike
# with OI above this becomes an OI wall. Lower thresholds catch more walls
# (with more noise); higher thresholds catch fewer (potentially missing
# real walls). Calibration may revisit this in Phase 4.
DEFAULT_PERCENTILE_THRESHOLD = 0.90


def _percentile_value(values: Sequence[float], q: float) -> float:
    """Linear-interpolation percentile of a non-empty numeric sequence.

    Matches NumPy's default ``percentile`` ("linear" interpolation) without
    importing NumPy (the engine has no NumPy dependency at this layer).
    `q` is in `[0, 1]`.
    """
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n == 0:
        # Defensive — callers filter to non-empty before invoking this helper.
        raise ValueError("_percentile_value: empty sequence")
    if n == 1:
        return sorted_vals[0]
    rank = q * (n - 1)
    lower_idx = int(rank)
    upper_idx = min(lower_idx + 1, n - 1)
    frac = rank - lower_idx
    return sorted_vals[lower_idx] + frac * (sorted_vals[upper_idx] - sorted_vals[lower_idx])


def compute_oi_walls(
    *,
    contracts: Sequence[OptionContract],
    spot: float,
    expiry_focus: Sequence[date],
    percentile_threshold: float = DEFAULT_PERCENTILE_THRESHOLD,
) -> OiWalls:
    """OI-derived support / resistance levels around spot.

    Args:
        contracts: Sequence of option-chain rows. Typically
                   `chain_snapshot.contracts`. Contracts outside
                   `expiry_focus` are filtered out internally; callers
                   may pass the full chain.
        spot: Current underlying spot. Must be > 0.
        expiry_focus: Iterable of `date` values naming the expiries to
                      consider. Only contracts whose `expiry` is in this
                      set contribute. Must be non-empty.
        percentile_threshold: Quantile of the per-strike OI distribution
                              defining "large OI". Must be in `[0, 1)`.
                              Default 0.90 (top decile, per §9.3).

    Returns:
        `OiWalls` (from `engine.scoring.structure`) with `support`,
        `resistance`, `support_oi`, `resistance_oi`, and `total_oi`
        populated. Either or both walls may be `None`.

    Raises:
        ValueError: `spot` <= 0, `expiry_focus` empty, no contracts at
                    any focus expiry, or `percentile_threshold` outside
                    `[0, 1)`.
    """
    if spot <= 0.0:
        raise ValueError(f"compute_oi_walls: spot must be > 0; got {spot}")
    if not 0.0 <= percentile_threshold < 1.0:
        raise ValueError(
            f"compute_oi_walls: percentile_threshold must be in [0, 1); "
            f"got {percentile_threshold}"
        )

    focus = set(expiry_focus)
    if not focus:
        raise ValueError(
            "compute_oi_walls: expiry_focus must contain at least one expiry"
        )

    relevant = [c for c in contracts if c.expiry in focus]
    if not relevant:
        raise ValueError(
            f"compute_oi_walls: no contracts present for the requested "
            f"expiry_focus ({sorted(focus)})"
        )

    # Aggregate OI per strike (sum across calls + puts).
    per_strike_oi: dict[float, int] = {}
    for c in relevant:
        per_strike_oi[c.strike] = per_strike_oi.get(c.strike, 0) + c.open_interest

    total_oi = sum(per_strike_oi.values())

    if not per_strike_oi:
        # Defensive — `relevant` is non-empty so per_strike_oi must be too,
        # but guard the helper call anyway.
        return OiWalls(support=None, resistance=None, total_oi=total_oi)

    # Threshold = percentile of per-strike OI. A strike counts as a wall
    # only when its OI is STRICTLY ABOVE the threshold (per plan §9.3:
    # "find strikes with OI > 90th percentile"). The strict-above rule
    # naturally handles flat distributions (no strike exceeds its own
    # percentile, so no walls emerge). The trade-off is that when
    # multiple strikes tie at the very top of the OI distribution, they
    # sit AT the percentile rather than above it, and none are reported
    # as walls. This is the conservative reading the plan prescribes;
    # downstream consumers can lower `percentile_threshold` (e.g. to
    # 0.75 or 0.60) when they want to catch tied peaks.
    oi_values = list(per_strike_oi.values())
    threshold = _percentile_value(oi_values, percentile_threshold)

    qualifying = {k: oi for k, oi in per_strike_oi.items() if oi > threshold}

    support: float | None = None
    resistance: float | None = None
    support_oi = 0
    resistance_oi = 0

    for k, oi in qualifying.items():
        if k < spot:
            if support is None or k > support:
                support = k
                support_oi = oi
        elif k > spot:
            if resistance is None or k < resistance:
                resistance = k
                resistance_oi = oi
        # k == spot is neither support nor resistance (a wall ON spot
        # provides no directional pressure).

    return OiWalls(
        support=support,
        resistance=resistance,
        support_oi=support_oi,
        resistance_oi=resistance_oi,
        total_oi=total_oi,
    )
