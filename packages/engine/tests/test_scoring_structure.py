"""Options-structure scoring primitive tests (M1.4a)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from engine.scoring import OiWalls, StructureScoreResult, structure_score

# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------


def _walls(
    *,
    support: float | None = None,
    resistance: float | None = None,
) -> OiWalls:
    return OiWalls(support=support, resistance=resistance)


# ----------------------------------------------------------------------
# happy paths — hand-computed references
# ----------------------------------------------------------------------


def test_structure_score_pinned_to_max_pain_at_opex() -> None:
    """Spot exactly on max_pain, both walls at +/-EM, opex tomorrow, tight EM.

    Components:
        wall_proximity:  walls at exactly 1·EM away, normalized by 2·EM
                         → 1 - 0.5 = 0.5 each side; min distance = same.
                         result = clip01(1 - 0.04 / (2 · 0.04)) = 0.5
        pin_alignment:   spot == max_pain → distance 0
                         result = clip01(1 - 0.0 / 0.04) = 1.0
        opex_proximity:  dte = 1 ≤ NEAR (2) → 1.0
        em_containment:  EM = 0.04, between TIGHT (0.02) and WIDE (0.10)
                         result = (0.10 - 0.04) / (0.10 - 0.02) = 0.75

    score = 0.30·0.5 + 0.25·1.0 + 0.20·1.0 + 0.25·0.75
          = 0.15 + 0.25 + 0.20 + 0.1875 = 0.7875
    """
    walls = _walls(support=96.0, resistance=104.0)
    result = structure_score(
        oi_walls=walls,
        max_pain=100.0,
        spot=100.0,
        expected_move_pct=0.04,
        dte_to_nearest_opex=1,
    )
    assert isinstance(result, StructureScoreResult)
    assert result.breakdown["wall_proximity"] == pytest.approx(0.5, abs=1e-12)
    assert result.breakdown["pin_alignment"] == pytest.approx(1.0, abs=1e-12)
    assert result.breakdown["opex_proximity"] == pytest.approx(1.0, abs=1e-12)
    assert result.breakdown["em_containment"] == pytest.approx(0.75, abs=1e-12)
    assert result.score == pytest.approx(0.7875, abs=1e-12)


def test_structure_score_no_walls_far_pin_far_opex_wide_em() -> None:
    """Maximally non-structural environment → score = 0.0."""
    walls = OiWalls(support=None, resistance=None)
    result = structure_score(
        oi_walls=walls,
        max_pain=70.0,  # 30% below spot — far outside any reasonable EM
        spot=100.0,
        expected_move_pct=0.20,  # well above WIDE (0.10)
        dte_to_nearest_opex=30,  # > FAR (14)
    )
    assert result.score == 0.0
    assert result.breakdown == {
        "wall_proximity": 0.0,
        "pin_alignment": 0.0,
        "opex_proximity": 0.0,
        "em_containment": 0.0,
    }


def test_structure_score_all_max() -> None:
    """Every component at its max → score = 1.0.

    Spot exactly on a wall AND on max_pain, opex today, EM at TIGHT.
    """
    walls = _walls(support=100.0, resistance=100.0)
    result = structure_score(
        oi_walls=walls,
        max_pain=100.0,
        spot=100.0,
        expected_move_pct=0.02,  # at TIGHT → em_containment = 1.0
        dte_to_nearest_opex=0,
    )
    assert result.score == pytest.approx(1.0, abs=1e-12)
    assert all(v == pytest.approx(1.0, abs=1e-12) for v in result.breakdown.values())


def test_structure_score_only_support_wall() -> None:
    """Resistance is None → wall_proximity uses support distance only."""
    walls = _walls(support=96.0, resistance=None)
    result = structure_score(
        oi_walls=walls,
        max_pain=120.0,  # far from spot, kills pin
        spot=100.0,
        expected_move_pct=0.04,
        dte_to_nearest_opex=14,  # at FAR threshold → 0.0 opex
    )
    # support is 4% below spot → distance_pct = 0.04; 0.04 / (2 · 0.04) = 0.5
    assert result.breakdown["wall_proximity"] == pytest.approx(0.5, abs=1e-12)
    assert result.breakdown["opex_proximity"] == pytest.approx(0.0, abs=1e-12)


def test_structure_score_only_resistance_wall() -> None:
    """Support is None → wall_proximity uses resistance distance only."""
    walls = _walls(support=None, resistance=104.0)
    result = structure_score(
        oi_walls=walls,
        max_pain=100.0,
        spot=100.0,
        expected_move_pct=0.04,
        dte_to_nearest_opex=7,
    )
    assert result.breakdown["wall_proximity"] == pytest.approx(0.5, abs=1e-12)


def test_structure_score_walls_picks_nearer() -> None:
    """When both walls are present, the nearer dominates the proximity term."""
    # Resistance is closer than support.
    walls = _walls(support=80.0, resistance=102.0)
    result = structure_score(
        oi_walls=walls,
        max_pain=100.0,
        spot=100.0,
        expected_move_pct=0.05,
        dte_to_nearest_opex=7,
    )
    # nearer distance_pct = 0.02; 0.02 / (2 · 0.05) = 0.20
    # wall_proximity = 1 - 0.20 = 0.80
    assert result.breakdown["wall_proximity"] == pytest.approx(0.80, abs=1e-12)


# ----------------------------------------------------------------------
# zero-EM degenerate path — both wall_proximity and pin_alignment branch
# ----------------------------------------------------------------------


def test_structure_score_zero_em_spot_on_wall_and_pin() -> None:
    """EM = 0 (zero-DTE), spot exactly on wall and on pin → both 1.0."""
    walls = _walls(support=100.0, resistance=100.0)
    result = structure_score(
        oi_walls=walls,
        max_pain=100.0,
        spot=100.0,
        expected_move_pct=0.0,
        dte_to_nearest_opex=0,
    )
    assert result.breakdown["wall_proximity"] == 1.0
    assert result.breakdown["pin_alignment"] == 1.0
    assert result.breakdown["em_containment"] == 1.0


def test_structure_score_zero_em_spot_off_wall_and_pin() -> None:
    """EM = 0 but spot is NOT on the wall / pin → both 0.0 (no signal at zero-EM)."""
    walls = _walls(support=99.0, resistance=101.0)
    result = structure_score(
        oi_walls=walls,
        max_pain=99.0,
        spot=100.0,
        expected_move_pct=0.0,
        dte_to_nearest_opex=0,
    )
    assert result.breakdown["wall_proximity"] == 0.0
    assert result.breakdown["pin_alignment"] == 0.0


# ----------------------------------------------------------------------
# em_containment band exhaustion
# ----------------------------------------------------------------------


def test_structure_score_em_at_tight() -> None:
    """EM at TIGHT_PCT → em_containment = 1.0."""
    walls = _walls()
    result = structure_score(
        oi_walls=walls,
        max_pain=10000.0,
        spot=100.0,
        expected_move_pct=0.02,
        dte_to_nearest_opex=99,
    )
    assert result.breakdown["em_containment"] == pytest.approx(1.0, abs=1e-12)


def test_structure_score_em_at_wide() -> None:
    """EM at WIDE_PCT → em_containment = 0.0."""
    walls = _walls()
    result = structure_score(
        oi_walls=walls,
        max_pain=10000.0,
        spot=100.0,
        expected_move_pct=0.10,
        dte_to_nearest_opex=99,
    )
    assert result.breakdown["em_containment"] == pytest.approx(0.0, abs=1e-12)


def test_structure_score_em_midband() -> None:
    """EM = 0.06 → em_containment = (0.10 - 0.06) / (0.10 - 0.02) = 0.5."""
    walls = _walls()
    result = structure_score(
        oi_walls=walls,
        max_pain=10000.0,
        spot=100.0,
        expected_move_pct=0.06,
        dte_to_nearest_opex=99,
    )
    assert result.breakdown["em_containment"] == pytest.approx(0.5, abs=1e-12)


# ----------------------------------------------------------------------
# opex band exhaustion
# ----------------------------------------------------------------------


def test_structure_score_opex_inside_near() -> None:
    """dte == NEAR (2) → opex_proximity = 1.0."""
    walls = _walls()
    result = structure_score(
        oi_walls=walls,
        max_pain=10000.0,
        spot=100.0,
        expected_move_pct=0.30,
        dte_to_nearest_opex=2,
    )
    assert result.breakdown["opex_proximity"] == 1.0


def test_structure_score_opex_at_far() -> None:
    """dte == FAR (14) → opex_proximity = 0.0."""
    walls = _walls()
    result = structure_score(
        oi_walls=walls,
        max_pain=10000.0,
        spot=100.0,
        expected_move_pct=0.30,
        dte_to_nearest_opex=14,
    )
    assert result.breakdown["opex_proximity"] == 0.0


def test_structure_score_opex_midband() -> None:
    """dte = 8 → opex_proximity = (14 - 8) / (14 - 2) = 0.5."""
    walls = _walls()
    result = structure_score(
        oi_walls=walls,
        max_pain=10000.0,
        spot=100.0,
        expected_move_pct=0.30,
        dte_to_nearest_opex=8,
    )
    assert result.breakdown["opex_proximity"] == pytest.approx(0.5, abs=1e-12)


# ----------------------------------------------------------------------
# input validation
# ----------------------------------------------------------------------


def test_structure_score_zero_spot_raises() -> None:
    with pytest.raises(ValueError, match="spot must be > 0"):
        structure_score(
            oi_walls=_walls(),
            max_pain=100.0,
            spot=0.0,
            expected_move_pct=0.04,
            dte_to_nearest_opex=7,
        )


def test_structure_score_negative_spot_raises() -> None:
    with pytest.raises(ValueError, match="spot must be > 0"):
        structure_score(
            oi_walls=_walls(),
            max_pain=100.0,
            spot=-1.0,
            expected_move_pct=0.04,
            dte_to_nearest_opex=7,
        )


def test_structure_score_zero_max_pain_raises() -> None:
    with pytest.raises(ValueError, match="max_pain must be > 0"):
        structure_score(
            oi_walls=_walls(),
            max_pain=0.0,
            spot=100.0,
            expected_move_pct=0.04,
            dte_to_nearest_opex=7,
        )


def test_structure_score_negative_em_raises() -> None:
    with pytest.raises(ValueError, match="expected_move_pct must be >= 0"):
        structure_score(
            oi_walls=_walls(),
            max_pain=100.0,
            spot=100.0,
            expected_move_pct=-0.01,
            dte_to_nearest_opex=7,
        )


def test_structure_score_negative_dte_raises() -> None:
    with pytest.raises(ValueError, match="dte_to_nearest_opex must be >= 0"):
        structure_score(
            oi_walls=_walls(),
            max_pain=100.0,
            spot=100.0,
            expected_move_pct=0.04,
            dte_to_nearest_opex=-1,
        )


def test_structure_score_breakdown_keys_stable() -> None:
    """Breakdown exposes the same four keys, in the same order, every call."""
    result = structure_score(
        oi_walls=_walls(support=99.0, resistance=101.0),
        max_pain=100.0,
        spot=100.0,
        expected_move_pct=0.05,
        dte_to_nearest_opex=5,
    )
    assert list(result.breakdown.keys()) == [
        "wall_proximity",
        "pin_alignment",
        "opex_proximity",
        "em_containment",
    ]


# ----------------------------------------------------------------------
# property tests
# ----------------------------------------------------------------------


@given(
    spot=st.floats(min_value=1.0, max_value=10000.0, allow_nan=False),
    max_pain=st.floats(min_value=0.5, max_value=20000.0, allow_nan=False),
    em_pct=st.floats(min_value=0.0, max_value=0.50, allow_nan=False),
    dte=st.integers(min_value=0, max_value=120),
    support=st.one_of(st.none(), st.floats(min_value=0.5, max_value=20000.0, allow_nan=False)),
    resistance=st.one_of(st.none(), st.floats(min_value=0.5, max_value=20000.0, allow_nan=False)),
)
def test_structure_score_always_in_unit_interval(
    spot: float,
    max_pain: float,
    em_pct: float,
    dte: int,
    support: float | None,
    resistance: float | None,
) -> None:
    walls = OiWalls(support=support, resistance=resistance)
    result = structure_score(
        oi_walls=walls,
        max_pain=max_pain,
        spot=spot,
        expected_move_pct=em_pct,
        dte_to_nearest_opex=dte,
    )
    assert 0.0 <= result.score <= 1.0
    for v in result.breakdown.values():
        assert 0.0 <= v <= 1.0


@given(
    base_dte=st.integers(min_value=2, max_value=13),
    delta=st.integers(min_value=1, max_value=5),
)
def test_structure_score_opex_proximity_monotonic(
    base_dte: int, delta: int
) -> None:
    """Larger dte_to_nearest_opex cannot increase the opex_proximity component."""
    walls = _walls()
    low = structure_score(
        oi_walls=walls,
        max_pain=100.0,
        spot=100.0,
        expected_move_pct=0.05,
        dte_to_nearest_opex=base_dte,
    )
    high = structure_score(
        oi_walls=walls,
        max_pain=100.0,
        spot=100.0,
        expected_move_pct=0.05,
        dte_to_nearest_opex=base_dte + delta,
    )
    assert high.breakdown["opex_proximity"] <= low.breakdown["opex_proximity"] + 1e-12
