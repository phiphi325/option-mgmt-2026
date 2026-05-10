"""Gamma-score primitive tests (M1.5a).

Per plan v1.2 §17 M1.5a (size S, 100% line coverage on `engine.scoring/`)
and §9.11 (Scoring Functions Module spec).
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from engine.scoring import GammaScoreResult, GammaWall, gamma_score

# ----------------------------------------------------------------------
# happy paths — hand-computed references
# ----------------------------------------------------------------------


def test_gamma_score_neutral_proxy_no_walls() -> None:
    """Zero proxy + no walls → score=0, sign=0."""
    result = gamma_score(
        dealer_gamma_proxy=0.0,
        spot=100.0,
        gamma_walls=[],
    )
    assert isinstance(result, GammaScoreResult)
    assert result.score == 0.0
    assert result.sign == 0
    assert result.breakdown == {"proxy_magnitude": 0.0, "walls_magnitude": 0.0}


def test_gamma_score_amplifier_no_walls() -> None:
    """Short-gamma proxy + no walls → score = |proxy| / (spot · 10_000), sign = -1.

    spot = 100, proxy = -200_000. denom = 100 · 10_000 = 1_000_000.
    proxy_magnitude = |−200_000| / 1_000_000 = 0.2.
    No walls → score = 0.2 directly (no weight redistribution).
    """
    result = gamma_score(
        dealer_gamma_proxy=-200_000.0,
        spot=100.0,
        gamma_walls=[],
    )
    assert result.score == pytest.approx(0.2, abs=1e-12)
    assert result.sign == -1
    assert result.breakdown["proxy_magnitude"] == pytest.approx(0.2, abs=1e-12)
    assert result.breakdown["walls_magnitude"] == 0.0


def test_gamma_score_dampener_no_walls() -> None:
    """Long-gamma proxy → sign = +1."""
    result = gamma_score(
        dealer_gamma_proxy=+200_000.0,
        spot=100.0,
        gamma_walls=[],
    )
    assert result.score == pytest.approx(0.2, abs=1e-12)
    assert result.sign == +1


def test_gamma_score_proxy_saturates_at_one() -> None:
    """Huge proxy magnitude → proxy_magnitude clips at 1.0."""
    result = gamma_score(
        dealer_gamma_proxy=-1e12,
        spot=100.0,
        gamma_walls=[],
    )
    assert result.score == 1.0
    assert result.sign == -1


def test_gamma_score_with_walls_blends_components() -> None:
    """Proxy = 500_000, spot = 100, single wall with gamma_exposure = 300_000.

    denom = 100 · 10_000 = 1_000_000.
    proxy_magnitude = 500_000 / 1_000_000 = 0.5.
    avg_wall_exposure = 300_000 / 1 = 300_000.
    walls_magnitude = 300_000 / 1_000_000 = 0.3.
    score = 0.7 · 0.5 + 0.3 · 0.3 = 0.35 + 0.09 = 0.44.
    """
    result = gamma_score(
        dealer_gamma_proxy=-500_000.0,
        spot=100.0,
        gamma_walls=[GammaWall(strike=105.0, gamma_exposure=-300_000.0)],
    )
    assert result.score == pytest.approx(0.44, abs=1e-12)
    assert result.sign == -1
    assert result.breakdown["proxy_magnitude"] == pytest.approx(0.5, abs=1e-12)
    assert result.breakdown["walls_magnitude"] == pytest.approx(0.3, abs=1e-12)


def test_gamma_score_walls_use_absolute_exposure() -> None:
    """Wall gamma_exposure sign does not affect walls_magnitude (only |·|)."""
    positive_wall = GammaWall(strike=105.0, gamma_exposure=+400_000.0)
    negative_wall = GammaWall(strike=105.0, gamma_exposure=-400_000.0)
    r_pos = gamma_score(
        dealer_gamma_proxy=0.0,
        spot=100.0,
        gamma_walls=[positive_wall],
    )
    r_neg = gamma_score(
        dealer_gamma_proxy=0.0,
        spot=100.0,
        gamma_walls=[negative_wall],
    )
    # Walls component is the same regardless of sign.
    assert r_pos.breakdown["walls_magnitude"] == r_neg.breakdown["walls_magnitude"]
    assert r_pos.score == r_neg.score


def test_gamma_score_multiple_walls_averaged() -> None:
    """walls_magnitude uses the *average* absolute exposure, not the sum."""
    walls = [
        GammaWall(strike=95.0, gamma_exposure=400_000.0),
        GammaWall(strike=105.0, gamma_exposure=200_000.0),
    ]
    # avg = (400_000 + 200_000) / 2 = 300_000
    # walls_magnitude = 300_000 / (100 · 10_000) = 0.3
    result = gamma_score(
        dealer_gamma_proxy=0.0,
        spot=100.0,
        gamma_walls=walls,
    )
    assert result.breakdown["walls_magnitude"] == pytest.approx(0.3, abs=1e-12)


def test_gamma_score_zero_proxy_with_walls() -> None:
    """Proxy = 0 but walls present → score positive, sign = 0."""
    result = gamma_score(
        dealer_gamma_proxy=0.0,
        spot=100.0,
        gamma_walls=[GammaWall(strike=105.0, gamma_exposure=200_000.0)],
    )
    # proxy_magnitude = 0; walls_magnitude = 200_000 / 1_000_000 = 0.2
    # score = 0.7 · 0 + 0.3 · 0.2 = 0.06
    assert result.score == pytest.approx(0.06, abs=1e-12)
    assert result.sign == 0


def test_gamma_score_walls_clip_to_one() -> None:
    """An enormous wall exposure saturates walls_magnitude at 1.0."""
    walls = [GammaWall(strike=105.0, gamma_exposure=1e12)]
    result = gamma_score(
        dealer_gamma_proxy=-1e12,
        spot=100.0,
        gamma_walls=walls,
    )
    assert result.breakdown["proxy_magnitude"] == 1.0
    assert result.breakdown["walls_magnitude"] == 1.0
    # score = clip01(0.7 · 1 + 0.3 · 1) = 1.0
    assert result.score == 1.0


def test_gamma_score_breakdown_keys_stable() -> None:
    """Breakdown exposes the same two keys in the same order, every call."""
    r = gamma_score(
        dealer_gamma_proxy=-100_000.0,
        spot=100.0,
        gamma_walls=[GammaWall(strike=110.0, gamma_exposure=50_000.0)],
    )
    assert list(r.breakdown.keys()) == ["proxy_magnitude", "walls_magnitude"]


# ----------------------------------------------------------------------
# input validation
# ----------------------------------------------------------------------


def test_gamma_score_zero_spot_raises() -> None:
    with pytest.raises(ValueError, match="spot must be > 0"):
        gamma_score(dealer_gamma_proxy=100.0, spot=0.0, gamma_walls=[])


def test_gamma_score_negative_spot_raises() -> None:
    with pytest.raises(ValueError, match="spot must be > 0"):
        gamma_score(dealer_gamma_proxy=100.0, spot=-1.0, gamma_walls=[])


# ----------------------------------------------------------------------
# property tests — score in [0, 1], sign in {-1, 0, +1}
# ----------------------------------------------------------------------


@given(
    proxy=st.floats(min_value=-1e10, max_value=1e10, allow_nan=False, allow_infinity=False),
    spot=st.floats(min_value=1.0, max_value=10_000.0, allow_nan=False),
    walls_data=st.lists(
        st.tuples(
            st.floats(min_value=1.0, max_value=10_000.0, allow_nan=False),
            st.floats(min_value=-1e10, max_value=1e10, allow_nan=False, allow_infinity=False),
        ),
        min_size=0,
        max_size=20,
    ),
)
def test_gamma_score_always_in_unit_interval(
    proxy: float, spot: float, walls_data: list[tuple[float, float]]
) -> None:
    walls = [GammaWall(strike=k, gamma_exposure=g) for (k, g) in walls_data]
    r = gamma_score(dealer_gamma_proxy=proxy, spot=spot, gamma_walls=walls)
    assert 0.0 <= r.score <= 1.0
    assert 0.0 <= r.breakdown["proxy_magnitude"] <= 1.0
    assert 0.0 <= r.breakdown["walls_magnitude"] <= 1.0
    assert r.sign in {-1, 0, +1}


@given(
    abs_proxy=st.floats(min_value=0.0, max_value=1e9, allow_nan=False),
    spot=st.floats(min_value=1.0, max_value=10_000.0, allow_nan=False),
)
def test_gamma_score_sign_symmetry_no_walls(abs_proxy: float, spot: float) -> None:
    """Without walls, |proxy| → identical score; sign flips with proxy sign."""
    pos = gamma_score(dealer_gamma_proxy=+abs_proxy, spot=spot, gamma_walls=[])
    neg = gamma_score(dealer_gamma_proxy=-abs_proxy, spot=spot, gamma_walls=[])
    assert pos.score == pytest.approx(neg.score)
    if abs_proxy > 0:
        assert pos.sign == +1
        assert neg.sign == -1
    else:
        assert pos.sign == 0
        assert neg.sign == 0


@given(
    proxy=st.floats(min_value=-1e9, max_value=1e9, allow_nan=False),
    spot=st.floats(min_value=1.0, max_value=10_000.0, allow_nan=False),
)
def test_gamma_score_sign_matches_proxy_sign(proxy: float, spot: float) -> None:
    """Sign field is strictly the sign of `dealer_gamma_proxy`."""
    r = gamma_score(dealer_gamma_proxy=proxy, spot=spot, gamma_walls=[])
    if proxy > 0:
        assert r.sign == +1
    elif proxy < 0:
        assert r.sign == -1
    else:
        assert r.sign == 0
