"""IV-favorability scoring primitive tests (M1.4a)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from engine.scoring import IvScoreResult, iv_score

# ----------------------------------------------------------------------
# happy paths — hand-computed references
# ----------------------------------------------------------------------


def test_iv_score_all_zero_inputs() -> None:
    """Zero rank, zero percentile, zero IV, zero HV → score = 0.5 · 0.30.

    Formula:
        rank      = 0.0
        percentile = 0.0
        hv == 0   → premium_component = 0.5 (constant-prices fallback)
        score = 0.40·0 + 0.30·0 + 0.30·0.5 = 0.15
    """
    result = iv_score(iv_rank=0.0, iv_percentile=0.0, hv_30=0.0, atm_iv_30d=0.0)
    assert isinstance(result, IvScoreResult)
    assert result.score == pytest.approx(0.15, abs=1e-12)
    assert result.breakdown == {"rank": 0.0, "percentile": 0.0, "iv_hv_premium": 0.5}


def test_iv_score_all_max_inputs() -> None:
    """Rank 1, percentile 1, IV/HV ratio above ceiling → score = 1.0."""
    result = iv_score(
        iv_rank=1.0, iv_percentile=1.0, hv_30=0.10, atm_iv_30d=0.30
    )
    # ratio = 3.0 → premium_component = clip01((3.0 - 0.7) / 0.8) = 1.0
    assert result.score == pytest.approx(1.0, abs=1e-12)
    assert result.breakdown == {"rank": 1.0, "percentile": 1.0, "iv_hv_premium": 1.0}


def test_iv_score_only_rank_at_max() -> None:
    """Only rank component active → score = 0.40 (the rank weight).

    With hv=0 (premium fallback to 0.5), the premium component contributes
    0.30·0.5 = 0.15. Add rank = 0.40·1.0 = 0.40 and percentile = 0.0:
        total = 0.55.
    """
    result = iv_score(iv_rank=1.0, iv_percentile=0.0, hv_30=0.0, atm_iv_30d=0.0)
    assert result.score == pytest.approx(0.55, abs=1e-12)


def test_iv_score_only_percentile_at_max() -> None:
    """Only percentile component active → score = 0.30 + 0.15 (premium fallback)."""
    result = iv_score(iv_rank=0.0, iv_percentile=1.0, hv_30=0.0, atm_iv_30d=0.0)
    assert result.score == pytest.approx(0.45, abs=1e-12)


def test_iv_score_iv_hv_parity() -> None:
    """IV = HV (ratio = 1.0) → premium_component = (1.0 - 0.7) / 0.8 = 0.375.

    With rank = 0 and percentile = 0:
        score = 0.30 · 0.375 = 0.1125.
    """
    result = iv_score(
        iv_rank=0.0, iv_percentile=0.0, hv_30=0.20, atm_iv_30d=0.20
    )
    assert result.breakdown["iv_hv_premium"] == pytest.approx(0.375, abs=1e-12)
    assert result.score == pytest.approx(0.1125, abs=1e-12)


def test_iv_score_iv_hv_at_floor() -> None:
    """IV/HV ratio at floor (0.7) → premium_component = 0.0."""
    result = iv_score(
        iv_rank=0.0, iv_percentile=0.0, hv_30=1.0, atm_iv_30d=0.7
    )
    assert result.breakdown["iv_hv_premium"] == pytest.approx(0.0, abs=1e-12)


def test_iv_score_iv_hv_below_floor() -> None:
    """IV/HV ratio below floor (clipped to 0.0) → premium_component = 0.0."""
    result = iv_score(
        iv_rank=0.0, iv_percentile=0.0, hv_30=1.0, atm_iv_30d=0.1
    )
    assert result.breakdown["iv_hv_premium"] == pytest.approx(0.0, abs=1e-12)


def test_iv_score_iv_hv_at_ceiling() -> None:
    """IV/HV ratio at ceiling (1.5) → premium_component = 1.0."""
    result = iv_score(
        iv_rank=0.0, iv_percentile=0.0, hv_30=0.20, atm_iv_30d=0.30
    )
    assert result.breakdown["iv_hv_premium"] == pytest.approx(1.0, abs=1e-12)


def test_iv_score_breakdown_keys_stable() -> None:
    """The breakdown dict always exposes the same three keys, in the same order."""
    result = iv_score(
        iv_rank=0.5, iv_percentile=0.5, hv_30=0.20, atm_iv_30d=0.25
    )
    assert list(result.breakdown.keys()) == ["rank", "percentile", "iv_hv_premium"]


# ----------------------------------------------------------------------
# input validation
# ----------------------------------------------------------------------


def test_iv_score_iv_rank_below_zero_raises() -> None:
    with pytest.raises(ValueError, match="iv_rank must be in"):
        iv_score(iv_rank=-0.01, iv_percentile=0.5, hv_30=0.20, atm_iv_30d=0.25)


def test_iv_score_iv_rank_above_one_raises() -> None:
    with pytest.raises(ValueError, match="iv_rank must be in"):
        iv_score(iv_rank=1.01, iv_percentile=0.5, hv_30=0.20, atm_iv_30d=0.25)


def test_iv_score_iv_percentile_below_zero_raises() -> None:
    with pytest.raises(ValueError, match="iv_percentile must be in"):
        iv_score(iv_rank=0.5, iv_percentile=-0.01, hv_30=0.20, atm_iv_30d=0.25)


def test_iv_score_iv_percentile_above_one_raises() -> None:
    with pytest.raises(ValueError, match="iv_percentile must be in"):
        iv_score(iv_rank=0.5, iv_percentile=1.5, hv_30=0.20, atm_iv_30d=0.25)


def test_iv_score_negative_hv_raises() -> None:
    with pytest.raises(ValueError, match="hv_30 must be >= 0"):
        iv_score(iv_rank=0.5, iv_percentile=0.5, hv_30=-0.01, atm_iv_30d=0.25)


def test_iv_score_negative_atm_iv_raises() -> None:
    with pytest.raises(ValueError, match="atm_iv_30d must be >= 0"):
        iv_score(iv_rank=0.5, iv_percentile=0.5, hv_30=0.20, atm_iv_30d=-0.01)


# ----------------------------------------------------------------------
# property tests — score in [0, 1] always; monotonicity in inputs
# ----------------------------------------------------------------------


@given(
    rank=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    percentile=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    hv=st.floats(min_value=0.0, max_value=2.0, allow_nan=False),
    atm_iv=st.floats(min_value=0.0, max_value=2.0, allow_nan=False),
)
def test_iv_score_always_in_unit_interval(
    rank: float, percentile: float, hv: float, atm_iv: float
) -> None:
    result = iv_score(iv_rank=rank, iv_percentile=percentile, hv_30=hv, atm_iv_30d=atm_iv)
    assert 0.0 <= result.score <= 1.0
    for component in result.breakdown.values():
        assert 0.0 <= component <= 1.0


@given(
    base_rank=st.floats(min_value=0.0, max_value=0.95, allow_nan=False),
    delta=st.floats(min_value=0.01, max_value=0.05, allow_nan=False),
    percentile=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    hv=st.floats(min_value=0.05, max_value=2.0, allow_nan=False),
    atm_iv=st.floats(min_value=0.0, max_value=2.0, allow_nan=False),
)
def test_iv_score_monotonic_in_iv_rank(
    base_rank: float,
    delta: float,
    percentile: float,
    hv: float,
    atm_iv: float,
) -> None:
    """Holding all else fixed, raising iv_rank cannot lower the score."""
    higher_rank = min(1.0, base_rank + delta)
    low = iv_score(
        iv_rank=base_rank, iv_percentile=percentile, hv_30=hv, atm_iv_30d=atm_iv
    )
    high = iv_score(
        iv_rank=higher_rank, iv_percentile=percentile, hv_30=hv, atm_iv_30d=atm_iv
    )
    assert high.score >= low.score - 1e-12


@given(
    rank=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    base_pct=st.floats(min_value=0.0, max_value=0.95, allow_nan=False),
    delta=st.floats(min_value=0.01, max_value=0.05, allow_nan=False),
    hv=st.floats(min_value=0.05, max_value=2.0, allow_nan=False),
    atm_iv=st.floats(min_value=0.0, max_value=2.0, allow_nan=False),
)
def test_iv_score_monotonic_in_iv_percentile(
    rank: float,
    base_pct: float,
    delta: float,
    hv: float,
    atm_iv: float,
) -> None:
    """Holding all else fixed, raising iv_percentile cannot lower the score."""
    higher_pct = min(1.0, base_pct + delta)
    low = iv_score(
        iv_rank=rank, iv_percentile=base_pct, hv_30=hv, atm_iv_30d=atm_iv
    )
    high = iv_score(
        iv_rank=rank, iv_percentile=higher_pct, hv_30=hv, atm_iv_30d=atm_iv
    )
    assert high.score >= low.score - 1e-12


@given(
    rank=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    percentile=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    hv=st.floats(min_value=0.05, max_value=1.0, allow_nan=False),
    base_iv=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    delta=st.floats(min_value=0.01, max_value=0.5, allow_nan=False),
)
def test_iv_score_monotonic_in_atm_iv(
    rank: float, percentile: float, hv: float, base_iv: float, delta: float
) -> None:
    """Holding HV fixed, raising atm_iv cannot lower the score."""
    low = iv_score(
        iv_rank=rank, iv_percentile=percentile, hv_30=hv, atm_iv_30d=base_iv
    )
    high = iv_score(
        iv_rank=rank, iv_percentile=percentile, hv_30=hv, atm_iv_30d=base_iv + delta
    )
    assert high.score >= low.score - 1e-12
