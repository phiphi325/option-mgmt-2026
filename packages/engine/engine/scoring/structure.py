"""Options-structure scoring primitive.

Per plan v1.2 §9.11 (Scoring Functions Module) and §17 M1.4a.

`structure_score()` answers "how much do option positioning and
structural levels constrain spot's near-term path?" It blends four
signals derived from the option chain plus a known max-pain strike:

  wall_proximity   How close is spot to a meaningful OI wall, normalized
                   by the expected one-σ move? Within 1 EM of a wall →
                   significant signal; beyond 2 EM → noise.
  pin_alignment    How tightly is spot aligned with the max-pain strike,
                   normalized by EM? Tight alignment + nearby opex is
                   the textbook "pin" setup.
  opex_proximity   How close is the nearest monthly opex (in trading days)?
                   Pin force grows with proximity to opex; weak beyond
                   ~14 days.
  em_containment   How small is the expected move? A small EM means
                   structural levels matter more (positioning dominates
                   diffusion); a large EM means realized risk swamps
                   structure.

Weights (sum to 1.0):

    score = 0.30 · wall + 0.25 · pin + 0.20 · opex + 0.25 · em_containment

This module defines the `OiWalls` input type. The full computation of
`OiWalls` from a `ChainSnapshot` lives in the Flow Score Engine
(M1.5, per §9.3); `structure_score()` consumes the result. `OiWalls` is
defined here rather than in `engine.types` because it is an intermediate
computation result rather than an external input contract — the only
producers are engine modules, the only consumers are scoring functions.

Edge cases:

  - Both `support` and `resistance` are None → wall_proximity = 0.0
    (no S/R signal). Pin/opex/em components still contribute.
  - `expected_move_pct == 0.0` (zero-DTE) → wall_proximity and
    pin_alignment cap at their endpoints (any nonzero distance maps
    to 0; spot exactly at a wall maps to 1). em_containment maxes at 1.0.
  - Negative inputs (spot, max_pain, expected_move_pct, dte_to_nearest_opex)
    → ValueError. Callers must pass real, validated values.

Pure function (per ADR-0005).
"""

from __future__ import annotations

from dataclasses import dataclass

from engine._utils import clip01

# Weights — must sum to 1.0 so the composite stays bounded by [0, 1].
_W_WALL = 0.30
_W_PIN = 0.25
_W_OPEX = 0.20
_W_EM = 0.25

# Opex-proximity normalization. Pin force is generally weak more than
# 14 trading days from a monthly opex (≈ three weeks of calendar time);
# anything beyond that maps to 0.0. Two trading days or fewer maps to 1.0.
_OPEX_FAR_DAYS = 14
_OPEX_NEAR_DAYS = 2

# EM-containment normalization. A 10% expected move is "wide" (event-window
# territory for MSFT); a 2% move is "tight" (typical low-IV environment).
# Linear in between, clipped at the endpoints.
_EM_WIDE_PCT = 0.10
_EM_TIGHT_PCT = 0.02


@dataclass(frozen=True)
class OiWalls:
    """Open-interest support/resistance levels around spot.

    Computed by the Flow Score Engine (M1.5, per plan v1.2 §9.3) from a
    `ChainSnapshot`. The 90th-percentile-OI strikes act as proxies for
    structural support (highest large-OI strike strictly below spot) and
    resistance (lowest large-OI strike strictly above spot).

    Either side may be `None` when no strike crosses the OI threshold —
    e.g. very illiquid expiries, or chains where the largest OI sits on
    one side of spot. `structure_score()` treats one-sided walls
    correctly (uses the available side, scores the absent side as 0).

    `*_oi` and `total_oi` fields are not consumed by `structure_score()`
    today; they are carried for downstream consumers (Strike Selector
    rationale strings, Confidence Composer breakdowns).
    """

    support: float | None
    resistance: float | None
    support_oi: int = 0
    resistance_oi: int = 0
    total_oi: int = 0


@dataclass(frozen=True)
class StructureScoreResult:
    """Result of `structure_score()`. Score plus per-component breakdown.

    `breakdown` keys map 1:1 to the formula components.
    """

    score: float
    breakdown: dict[str, float]


def _wall_proximity_component(
    *,
    spot: float,
    walls: OiWalls,
    expected_move_pct: float,
) -> float:
    """How close is spot to its nearest OI wall, normalized by EM?

    Returns 1.0 when spot sits exactly on a wall, 0.0 when both walls are
    absent or both are more than 2 expected-moves away. Linear in between.
    Selects the *nearer* wall when both are present.
    """
    distances: list[float] = []
    if walls.support is not None:
        distances.append(abs(spot - walls.support) / spot)
    if walls.resistance is not None:
        distances.append(abs(spot - walls.resistance) / spot)
    if not distances:
        return 0.0
    nearest_dist_pct = min(distances)
    # Normalize against 2× EM. Within 0% of a wall → 1.0; at 2× EM → 0.0.
    # When EM is 0 (zero-DTE) any nonzero distance maps to 0.
    if expected_move_pct <= 0.0:
        return 1.0 if nearest_dist_pct == 0.0 else 0.0
    return clip01(1.0 - nearest_dist_pct / (2.0 * expected_move_pct))


def _pin_alignment_component(
    *,
    spot: float,
    max_pain: float,
    expected_move_pct: float,
) -> float:
    """How tightly is spot aligned with max_pain, normalized by EM?"""
    dist_pct = abs(spot - max_pain) / spot
    if expected_move_pct <= 0.0:
        return 1.0 if dist_pct == 0.0 else 0.0
    return clip01(1.0 - dist_pct / expected_move_pct)


def _opex_proximity_component(*, dte_to_nearest_opex: int) -> float:
    """How close is the nearest monthly opex? Maps `[NEAR, FAR]` to `[1, 0]`."""
    if dte_to_nearest_opex <= _OPEX_NEAR_DAYS:
        return 1.0
    if dte_to_nearest_opex >= _OPEX_FAR_DAYS:
        return 0.0
    return (_OPEX_FAR_DAYS - dte_to_nearest_opex) / (_OPEX_FAR_DAYS - _OPEX_NEAR_DAYS)


def _em_containment_component(*, expected_move_pct: float) -> float:
    """How small is the expected move? Maps `[TIGHT, WIDE]` to `[1, 0]`."""
    if expected_move_pct <= _EM_TIGHT_PCT:
        return 1.0
    if expected_move_pct >= _EM_WIDE_PCT:
        return 0.0
    return (_EM_WIDE_PCT - expected_move_pct) / (_EM_WIDE_PCT - _EM_TIGHT_PCT)


def structure_score(
    *,
    oi_walls: OiWalls,
    max_pain: float,
    spot: float,
    expected_move_pct: float,
    dte_to_nearest_opex: int,
) -> StructureScoreResult:
    """Composite options-structure score in [0, 1].

    Higher values indicate a more constrained structural environment —
    spot near walls, max-pain alignment, near opex, tight EM.

    Args:
        oi_walls: OI-derived support/resistance levels (M1.5 output).
                  Either side may be None.
        max_pain: Max-pain strike for the focus expiry. From
                  `engine.market_state.compute_max_pain()`.
        spot: Current spot. Must be > 0.
        expected_move_pct: One-σ expected move as a fraction (0.04 = 4%).
                           Must be >= 0.
        dte_to_nearest_opex: Trading days to the nearest monthly opex.
                             Must be >= 0.

    Returns:
        `StructureScoreResult` with `score` in [0, 1] and a `breakdown`
        dict carrying the individual component values.

    Raises:
        ValueError: `spot` <= 0, `max_pain` <= 0, `expected_move_pct` < 0,
                    or `dte_to_nearest_opex` < 0.
    """
    if spot <= 0.0:
        raise ValueError(f"structure_score: spot must be > 0; got {spot}")
    if max_pain <= 0.0:
        raise ValueError(f"structure_score: max_pain must be > 0; got {max_pain}")
    if expected_move_pct < 0.0:
        raise ValueError(
            f"structure_score: expected_move_pct must be >= 0; got {expected_move_pct}"
        )
    if dte_to_nearest_opex < 0:
        raise ValueError(
            f"structure_score: dte_to_nearest_opex must be >= 0; "
            f"got {dte_to_nearest_opex}"
        )

    wall_component = _wall_proximity_component(
        spot=spot,
        walls=oi_walls,
        expected_move_pct=expected_move_pct,
    )
    pin_component = _pin_alignment_component(
        spot=spot,
        max_pain=max_pain,
        expected_move_pct=expected_move_pct,
    )
    opex_component = _opex_proximity_component(
        dte_to_nearest_opex=dte_to_nearest_opex
    )
    em_component = _em_containment_component(expected_move_pct=expected_move_pct)

    score = clip01(
        _W_WALL * wall_component
        + _W_PIN * pin_component
        + _W_OPEX * opex_component
        + _W_EM * em_component
    )

    return StructureScoreResult(
        score=score,
        breakdown={
            "wall_proximity": wall_component,
            "pin_alignment": pin_component,
            "opex_proximity": opex_component,
            "em_containment": em_component,
        },
    )
