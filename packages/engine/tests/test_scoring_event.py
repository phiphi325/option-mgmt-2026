"""Event-uncertainty scoring primitive tests (M1.4a)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from engine.scoring import (
    EVENT_KIND_WEIGHTS,
    EventKind,
    EventScoreResult,
    EventStats,
    event_score,
)

# ----------------------------------------------------------------------
# happy paths — hand-computed references
# ----------------------------------------------------------------------


def test_event_score_no_event_zero() -> None:
    """No scheduled event → proximity gate collapses score to 0."""
    history = EventStats(avg_abs_return_pct=0.05)
    result = event_score(days_to_event=None, event_kind=None, event_history=history)
    assert isinstance(result, EventScoreResult)
    assert result.score == 0.0
    assert result.breakdown["proximity"] == 0.0


def test_event_score_far_event_zero() -> None:
    """Event 30+ days out → proximity = 0 → score = 0."""
    history = EventStats(avg_abs_return_pct=0.05)
    result = event_score(
        days_to_event=30, event_kind="earnings", event_history=history
    )
    assert result.score == 0.0
    assert result.breakdown["proximity"] == 0.0
    # kind_weight and magnitude still computed even when proximity gates score.
    assert result.breakdown["kind_weight"] == pytest.approx(1.0, abs=1e-12)
    assert result.breakdown["magnitude"] == pytest.approx(1.0, abs=1e-12)


def test_event_score_imminent_earnings_max() -> None:
    """0-day earnings, magnitude at threshold → score = 1.0.

    proximity = 1 - 0/30 = 1.0
    kind_weight = 1.0 (earnings)
    magnitude = clip01(0.05 / 0.05) = 1.0
    inner = 0.5·1.0 + 0.5·1.0 = 1.0
    score = clip01(1.0 · 1.0) = 1.0
    """
    history = EventStats(avg_abs_return_pct=0.05)
    result = event_score(
        days_to_event=0, event_kind="earnings", event_history=history
    )
    assert result.score == pytest.approx(1.0, abs=1e-12)


def test_event_score_imminent_fomc() -> None:
    """0-day FOMC, magnitude at threshold → score = 0.5·0.7 + 0.5·1.0 = 0.85."""
    history = EventStats(avg_abs_return_pct=0.05)
    result = event_score(
        days_to_event=0, event_kind="fomc", event_history=history
    )
    assert result.breakdown["kind_weight"] == pytest.approx(0.7, abs=1e-12)
    assert result.score == pytest.approx(0.85, abs=1e-12)


def test_event_score_proximity_midband() -> None:
    """15 days out → proximity = (30 - 15) / 30 = 0.5."""
    history = EventStats(avg_abs_return_pct=0.05)
    result = event_score(
        days_to_event=15, event_kind="earnings", event_history=history
    )
    # inner = 0.5·1.0 + 0.5·1.0 = 1.0; score = 0.5 · 1.0 = 0.5
    assert result.breakdown["proximity"] == pytest.approx(0.5, abs=1e-12)
    assert result.score == pytest.approx(0.5, abs=1e-12)


def test_event_score_negative_days_clamped_to_zero() -> None:
    """Negative days (event already past) clamps to 0 → proximity = 1.0.

    This is a defensive code path — the event-calendar service should
    advance past events promptly, but if it doesn't the engine should
    still produce a sensible answer.
    """
    history = EventStats(avg_abs_return_pct=0.05)
    result = event_score(
        days_to_event=-3, event_kind="earnings", event_history=history
    )
    assert result.breakdown["proximity"] == pytest.approx(1.0, abs=1e-12)


def test_event_score_unknown_kind_uses_default_weight() -> None:
    """Unknown event_kind string → default mid-tier weight (0.5)."""
    history = EventStats(avg_abs_return_pct=0.05)
    result = event_score(
        days_to_event=0,
        event_kind="bigfoot_sighting",
        event_history=history,
    )
    assert result.breakdown["kind_weight"] == pytest.approx(0.5, abs=1e-12)


def test_event_score_kind_none_uses_default_weight() -> None:
    """None event_kind (e.g. event scheduled but kind missing) → default weight."""
    history = EventStats(avg_abs_return_pct=0.05)
    result = event_score(
        days_to_event=5, event_kind=None, event_history=history
    )
    assert result.breakdown["kind_weight"] == pytest.approx(0.5, abs=1e-12)


def test_event_score_zero_magnitude_history() -> None:
    """Zero historical magnitude → magnitude component = 0.

    inner = 0.5·1.0 + 0.5·0.0 = 0.5
    score (0d earnings) = 1.0 · 0.5 = 0.5
    """
    history = EventStats(avg_abs_return_pct=0.0)
    result = event_score(
        days_to_event=0, event_kind="earnings", event_history=history
    )
    assert result.breakdown["magnitude"] == 0.0
    assert result.score == pytest.approx(0.5, abs=1e-12)


def test_event_score_huge_magnitude_history_clipped() -> None:
    """Magnitude well above threshold → clipped to 1.0."""
    history = EventStats(avg_abs_return_pct=0.50)
    result = event_score(
        days_to_event=0, event_kind="earnings", event_history=history
    )
    assert result.breakdown["magnitude"] == pytest.approx(1.0, abs=1e-12)


def test_event_score_known_kind_table_complete() -> None:
    """Every recognized EventKind is in the weights table at a value in [0, 1]."""
    for kind in EventKind:
        weight = EVENT_KIND_WEIGHTS[kind.value]
        assert 0.0 <= weight <= 1.0


def test_event_score_breakdown_keys_stable() -> None:
    """Breakdown exposes the same three keys, in the same order, every call."""
    history = EventStats(avg_abs_return_pct=0.05)
    result = event_score(
        days_to_event=7, event_kind="earnings", event_history=history
    )
    assert list(result.breakdown.keys()) == ["proximity", "kind_weight", "magnitude"]


# ----------------------------------------------------------------------
# input validation
# ----------------------------------------------------------------------


def test_event_score_negative_avg_return_raises() -> None:
    bad = EventStats(avg_abs_return_pct=-0.01)
    with pytest.raises(ValueError, match="avg_abs_return_pct must be >= 0"):
        event_score(days_to_event=0, event_kind="earnings", event_history=bad)


def test_event_score_negative_iv_runup_raises() -> None:
    bad = EventStats(avg_abs_return_pct=0.05, iv_runup_pct=-0.01)
    with pytest.raises(ValueError, match="iv_runup_pct must be >= 0"):
        event_score(days_to_event=0, event_kind="earnings", event_history=bad)


def test_event_score_negative_sample_count_raises() -> None:
    bad = EventStats(avg_abs_return_pct=0.05, sample_count=-1)
    with pytest.raises(ValueError, match="sample_count must be >= 0"):
        event_score(days_to_event=0, event_kind="earnings", event_history=bad)


# ----------------------------------------------------------------------
# property tests
# ----------------------------------------------------------------------


@given(
    days_to_event=st.one_of(st.none(), st.integers(min_value=-10, max_value=120)),
    event_kind=st.one_of(
        st.none(),
        st.sampled_from([k.value for k in EventKind]),
        st.text(min_size=1, max_size=20),
    ),
    avg_abs=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    iv_runup=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    samples=st.integers(min_value=0, max_value=100),
)
def test_event_score_always_in_unit_interval(
    days_to_event: int | None,
    event_kind: str | None,
    avg_abs: float,
    iv_runup: float,
    samples: int,
) -> None:
    history = EventStats(
        avg_abs_return_pct=avg_abs,
        iv_runup_pct=iv_runup,
        sample_count=samples,
    )
    result = event_score(
        days_to_event=days_to_event,
        event_kind=event_kind,
        event_history=history,
    )
    assert 0.0 <= result.score <= 1.0
    for v in result.breakdown.values():
        assert 0.0 <= v <= 1.0


@given(
    base_days=st.integers(min_value=0, max_value=29),
    delta=st.integers(min_value=1, max_value=10),
)
def test_event_score_proximity_monotonic_decreasing_in_days(
    base_days: int, delta: int
) -> None:
    """Holding kind + history fixed, more distant events cannot score higher."""
    history = EventStats(avg_abs_return_pct=0.04)
    near = event_score(
        days_to_event=base_days, event_kind="earnings", event_history=history
    )
    far = event_score(
        days_to_event=base_days + delta,
        event_kind="earnings",
        event_history=history,
    )
    assert far.score <= near.score + 1e-12


@given(
    days=st.integers(min_value=0, max_value=29),
    base_mag=st.floats(min_value=0.0, max_value=0.04, allow_nan=False),
    delta=st.floats(min_value=0.001, max_value=0.05, allow_nan=False),
)
def test_event_score_monotonic_in_magnitude(
    days: int, base_mag: float, delta: float
) -> None:
    """Holding all else fixed, larger historical moves cannot lower the score."""
    low = event_score(
        days_to_event=days,
        event_kind="earnings",
        event_history=EventStats(avg_abs_return_pct=base_mag),
    )
    high = event_score(
        days_to_event=days,
        event_kind="earnings",
        event_history=EventStats(avg_abs_return_pct=base_mag + delta),
    )
    assert high.score >= low.score - 1e-12
