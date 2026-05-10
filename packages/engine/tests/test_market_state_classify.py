"""Market State Engine `classify()` tests (M1.4).

Per plan v1.2 §17 M1.4 acceptance: 24 regime fixtures (4 per regime).
Per plan v1.2 §22.3 / §9.2: extended 18-input signature + per-regime
predicate sketches.

Tests are organized by section:
  - Per-regime fixtures (24 cases)
  - Tag generation
  - Tie-break behaviour
  - Echoed inputs
  - Input validation
  - Hypothesis property tests
"""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from engine.market_state import MarketStateResult, classify
from engine.regimes import Regime

# ----------------------------------------------------------------------
# Helpers — neutral baseline + per-test override pattern
# ----------------------------------------------------------------------


def _baseline() -> dict[str, Any]:
    """Neutral inputs that don't cleanly favor any regime.

    Each fixture overrides only the fields relevant to its target
    regime, keeping test bodies focused on the discriminating signal.
    """
    return {
        "spot": 100.0,
        "iv_rank": 0.50,
        "iv_percentile": 0.50,
        "hv_30": 0.20,
        "expected_move_pct": 0.04,
        "max_pain": 100.0,
        "pcr_volume": 1.0,
        "pcr_oi": 1.0,
        "days_to_next_event": None,
        "next_event_kind": None,
        "trend_strength": 0.5,
        "realized_vs_implied": 1.0,
        "days_since_event": None,
        "days_to_nearest_opex": 14,
        "iv_rank_change_1d": None,
        "gap_pct": None,
        "breakout_signal": 0.0,
        "oi_concentration_at_max_pain": 0.3,
    }


def _classify(**overrides: Any) -> MarketStateResult:
    inputs = _baseline()
    inputs.update(overrides)
    return classify(**inputs)


# ----------------------------------------------------------------------
# HIGH_IV_EVENT fixtures (4) — rich premium + scheduled near-term event
# ----------------------------------------------------------------------


def test_classify_high_iv_event_earnings_in_3d() -> None:
    r = _classify(
        iv_rank=0.80,
        iv_percentile=0.78,
        days_to_next_event=3,
        next_event_kind="earnings",
        max_pain=97.0,             # 3% off spot — kills HIGH_IV_PIN
        days_to_nearest_opex=20,
        realized_vs_implied=0.4,   # IV runup pre-event
    )
    assert r.regime is Regime.HIGH_IV_EVENT


def test_classify_high_iv_event_fomc_in_5d() -> None:
    r = _classify(
        iv_rank=0.78,
        iv_percentile=0.75,
        days_to_next_event=5,
        next_event_kind="fomc",
        max_pain=95.0,
        days_to_nearest_opex=15,
        realized_vs_implied=0.5,
    )
    assert r.regime is Regime.HIGH_IV_EVENT


def test_classify_high_iv_event_earnings_tomorrow_extreme_iv() -> None:
    r = _classify(
        iv_rank=0.92,
        iv_percentile=0.90,
        days_to_next_event=1,
        next_event_kind="earnings",
        max_pain=92.0,
        days_to_nearest_opex=8,
        realized_vs_implied=0.3,
    )
    assert r.regime is Regime.HIGH_IV_EVENT


def test_classify_high_iv_event_cpi_in_2d() -> None:
    r = _classify(
        iv_rank=0.85,
        iv_percentile=0.83,
        days_to_next_event=2,
        next_event_kind="cpi",
        max_pain=104.0,
        days_to_nearest_opex=20,
        realized_vs_implied=0.4,
    )
    assert r.regime is Regime.HIGH_IV_EVENT


# ----------------------------------------------------------------------
# HIGH_IV_PIN fixtures (4) — mid-high IV + tight max-pain alignment
# ----------------------------------------------------------------------


def test_classify_high_iv_pin_spot_on_pain_at_opex() -> None:
    r = _classify(
        iv_rank=0.68,
        iv_percentile=0.65,
        spot=100.0,
        max_pain=100.0,
        days_to_nearest_opex=0,
        realized_vs_implied=1.5,
        oi_concentration_at_max_pain=0.7,
    )
    assert r.regime is Regime.HIGH_IV_PIN


def test_classify_high_iv_pin_near_pin_dte_2() -> None:
    r = _classify(
        iv_rank=0.72,
        iv_percentile=0.70,
        spot=100.0,
        max_pain=100.5,
        days_to_nearest_opex=2,
        realized_vs_implied=1.5,
        oi_concentration_at_max_pain=0.65,
    )
    assert r.regime is Regime.HIGH_IV_PIN


def test_classify_high_iv_pin_dte_1() -> None:
    r = _classify(
        iv_rank=0.65,
        iv_percentile=0.62,
        spot=200.0,
        max_pain=200.0,
        days_to_nearest_opex=1,
        realized_vs_implied=1.5,
    )
    assert r.regime is Regime.HIGH_IV_PIN


def test_classify_high_iv_pin_tight_pin_dte_0() -> None:
    r = _classify(
        iv_rank=0.70,
        iv_percentile=0.68,
        spot=50.0,
        max_pain=49.85,            # 0.3% off — within pin tolerance
        days_to_nearest_opex=0,
        realized_vs_implied=1.4,
    )
    assert r.regime is Regime.HIGH_IV_PIN


# ----------------------------------------------------------------------
# LOW_IV_TREND fixtures (4) — low IV + sustained ADX
# ----------------------------------------------------------------------


def test_classify_low_iv_trend_strong_uptrend() -> None:
    r = _classify(
        iv_rank=0.20,
        iv_percentile=0.18,
        trend_strength=0.85,
        realized_vs_implied=0.6,   # realized lower than implied → not RANGE
    )
    assert r.regime is Regime.LOW_IV_TREND


def test_classify_low_iv_trend_strong_downtrend() -> None:
    r = _classify(
        iv_rank=0.15,
        iv_percentile=0.12,
        trend_strength=0.90,
        realized_vs_implied=0.5,
    )
    assert r.regime is Regime.LOW_IV_TREND


def test_classify_low_iv_trend_moderate() -> None:
    r = _classify(
        iv_rank=0.25,
        iv_percentile=0.22,
        trend_strength=0.75,
        realized_vs_implied=0.7,
    )
    assert r.regime is Regime.LOW_IV_TREND


def test_classify_low_iv_trend_max_adx() -> None:
    r = _classify(
        iv_rank=0.10,
        iv_percentile=0.08,
        trend_strength=1.0,
        realized_vs_implied=0.5,
    )
    assert r.regime is Regime.LOW_IV_TREND


# ----------------------------------------------------------------------
# LOW_IV_RANGE fixtures (4) — low IV + flat ADX + realized ≈ implied
# ----------------------------------------------------------------------


def test_classify_low_iv_range_flat_market() -> None:
    r = _classify(
        iv_rank=0.20,
        iv_percentile=0.18,
        trend_strength=0.10,
        realized_vs_implied=1.0,
    )
    assert r.regime is Regime.LOW_IV_RANGE


def test_classify_low_iv_range_dead_zone() -> None:
    r = _classify(
        iv_rank=0.18,
        iv_percentile=0.16,
        trend_strength=0.05,
        realized_vs_implied=0.95,
    )
    assert r.regime is Regime.LOW_IV_RANGE


def test_classify_low_iv_range_realized_close_to_implied() -> None:
    r = _classify(
        iv_rank=0.22,
        iv_percentile=0.20,
        trend_strength=0.20,
        realized_vs_implied=1.05,
    )
    assert r.regime is Regime.LOW_IV_RANGE


def test_classify_low_iv_range_zero_trend() -> None:
    r = _classify(
        iv_rank=0.25,
        iv_percentile=0.22,
        trend_strength=0.0,
        realized_vs_implied=1.0,
    )
    assert r.regime is Regime.LOW_IV_RANGE


# ----------------------------------------------------------------------
# BREAKOUT fixtures (4) — breakout_signal dominates
# ----------------------------------------------------------------------


def test_classify_breakout_strong_signal_no_event() -> None:
    r = _classify(
        iv_rank=0.40,
        iv_percentile=0.38,
        breakout_signal=0.95,
        trend_strength=0.5,
    )
    assert r.regime is Regime.BREAKOUT


def test_classify_breakout_max_signal() -> None:
    r = _classify(
        iv_rank=0.45,
        iv_percentile=0.43,
        breakout_signal=1.0,
        trend_strength=0.4,
    )
    assert r.regime is Regime.BREAKOUT


def test_classify_breakout_above_threshold() -> None:
    r = _classify(
        iv_rank=0.35,
        iv_percentile=0.33,
        breakout_signal=0.85,
        trend_strength=0.5,
    )
    assert r.regime is Regime.BREAKOUT


def test_classify_breakout_with_some_trend() -> None:
    r = _classify(
        iv_rank=0.30,
        iv_percentile=0.28,
        breakout_signal=0.92,
        trend_strength=0.6,
    )
    assert r.regime is Regime.BREAKOUT


# ----------------------------------------------------------------------
# POST_EVENT_REPRICE fixtures (4) — IV crush + price gap, days_since <= 1
# ----------------------------------------------------------------------


def test_classify_post_event_full_crush_gap_up() -> None:
    r = _classify(
        iv_rank=0.45,
        iv_percentile=0.40,
        days_since_event=0,
        iv_rank_change_1d=-0.25,   # 25 pp drop — fully crushed
        gap_pct=0.025,             # 2.5% gap up
    )
    assert r.regime is Regime.POST_EVENT_REPRICE


def test_classify_post_event_one_day_after_crush() -> None:
    r = _classify(
        iv_rank=0.40,
        iv_percentile=0.36,
        days_since_event=1,
        iv_rank_change_1d=-0.30,
        gap_pct=0.030,
    )
    assert r.regime is Regime.POST_EVENT_REPRICE


def test_classify_post_event_gap_down() -> None:
    r = _classify(
        iv_rank=0.42,
        iv_percentile=0.40,
        days_since_event=0,
        iv_rank_change_1d=-0.22,
        gap_pct=-0.025,            # negative gap (gap down) still triggers
    )
    assert r.regime is Regime.POST_EVENT_REPRICE


def test_classify_post_event_strong_crush_big_gap() -> None:
    r = _classify(
        iv_rank=0.38,
        iv_percentile=0.36,
        days_since_event=1,
        iv_rank_change_1d=-0.28,
        gap_pct=0.040,
    )
    assert r.regime is Regime.POST_EVENT_REPRICE


# ----------------------------------------------------------------------
# Tag generation
# ----------------------------------------------------------------------


def test_classify_tag_sell_vol_favorable_at_high_iv() -> None:
    r = _classify(iv_rank=0.75, days_to_next_event=3, next_event_kind="earnings")
    assert "sell_vol_favorable" in r.tags


def test_classify_tag_sell_vol_unfavorable_at_low_iv() -> None:
    r = _classify(iv_rank=0.25, trend_strength=0.1)
    assert "sell_vol_unfavorable" in r.tags


def test_classify_tag_event_in_nd_format() -> None:
    r = _classify(
        iv_rank=0.80,
        days_to_next_event=5,
        next_event_kind="earnings",
        max_pain=97.0,
        realized_vs_implied=0.4,
    )
    assert "event_in_5d" in r.tags


def test_classify_tag_event_dropped_when_far() -> None:
    r = _classify(days_to_next_event=30, next_event_kind="earnings")
    assert not any(t.startswith("event_in_") for t in r.tags)


def test_classify_tag_post_event_window() -> None:
    r = _classify(
        days_since_event=1,
        iv_rank_change_1d=-0.25,
        gap_pct=0.025,
    )
    assert "post_event_window" in r.tags


def test_classify_tag_pin_risk() -> None:
    r = _classify(
        iv_rank=0.65,
        spot=100.0,
        max_pain=100.3,            # 0.3% off — within 0.5%
        days_to_nearest_opex=3,    # within 5
    )
    assert "pin_risk" in r.tags


def test_classify_tag_pin_risk_not_set_when_far_dte() -> None:
    r = _classify(
        spot=100.0,
        max_pain=100.0,
        days_to_nearest_opex=20,
    )
    assert "pin_risk" not in r.tags


def test_classify_tag_breakout_active() -> None:
    r = _classify(breakout_signal=0.85)
    assert "breakout_active" in r.tags


def test_classify_tag_trending_high_adx() -> None:
    r = _classify(trend_strength=0.85)
    assert "trending" in r.tags
    assert "ranging" not in r.tags


def test_classify_tag_ranging_low_adx() -> None:
    r = _classify(trend_strength=0.10)
    assert "ranging" in r.tags
    assert "trending" not in r.tags


def test_classify_tag_concentrated_oi_at_pin() -> None:
    r = _classify(oi_concentration_at_max_pain=0.75)
    assert "concentrated_oi_at_pin" in r.tags


def test_classify_tags_returns_tuple_not_list() -> None:
    """`tags` field must be a tuple so MarketStateResult is hashable-shaped."""
    r = _classify()
    assert isinstance(r.tags, tuple)


# ----------------------------------------------------------------------
# Tie-break behaviour
# ----------------------------------------------------------------------


def test_classify_ties_resolve_to_higher_priority_event_over_pin() -> None:
    """When HIGH_IV_PIN scores higher than HIGH_IV_EVENT but within
    `_TIE_DELTA`, the priority list resolves toward HIGH_IV_EVENT
    (higher in TIE_BREAK_PRIORITY).

    Construction: iv_rank=0.80 + days_to_event=7 + spot==max_pain +
    dte=0 puts both regimes high. HIGH_IV_PIN scores ~0.952; HIGH_IV_EVENT
    scores ~0.866 — within ~0.087 of the leader, so the tie band picks
    up the lower-numerical-but-higher-priority HIGH_IV_EVENT.
    """
    r = _classify(
        iv_rank=0.80,
        iv_percentile=0.78,
        spot=100.0,
        max_pain=100.0,
        days_to_nearest_opex=0,
        days_to_next_event=7,
        next_event_kind="earnings",
        realized_vs_implied=0.5,
        oi_concentration_at_max_pain=0.6,
    )
    he = r.all_scores[Regime.HIGH_IV_EVENT]
    hp = r.all_scores[Regime.HIGH_IV_PIN]
    # PIN scores higher numerically but EVENT is within the tie band.
    assert hp > he, f"expected HIGH_IV_PIN > HIGH_IV_EVENT; got {hp=}, {he=}"
    assert hp - he < 0.10, f"expected within tie band; got delta {hp - he}"
    # Priority resolves toward HIGH_IV_EVENT despite PIN's numerical lead.
    assert r.regime is Regime.HIGH_IV_EVENT


def test_classify_regime_score_matches_all_scores() -> None:
    """`regime_score` is always the score that the chosen regime received,
    not the leader's score (relevant under tie-break)."""
    r = _classify(
        iv_rank=0.80,
        days_to_next_event=3,
        next_event_kind="earnings",
        max_pain=97.0,
        realized_vs_implied=0.4,
    )
    assert r.regime_score == pytest.approx(r.all_scores[r.regime], abs=1e-12)


# ----------------------------------------------------------------------
# Echoed inputs
# ----------------------------------------------------------------------


def test_classify_echoes_inputs_with_max_pain_delta() -> None:
    r = _classify(spot=100.0, max_pain=102.0)
    assert r.spot == 100.0
    assert r.max_pain == 102.0
    assert r.max_pain_delta_pct == pytest.approx(0.02, abs=1e-12)


def test_classify_echoes_optional_inputs() -> None:
    r = _classify(
        iv_rank_change_1d=-0.10,
        gap_pct=0.015,
        days_since_event=2,
        next_event_kind="fomc",
    )
    assert r.iv_rank_change_1d == -0.10
    assert r.gap_pct == 0.015
    assert r.days_since_event == 2
    assert r.next_event_kind == "fomc"


def test_classify_all_scores_has_all_six_regimes() -> None:
    r = _classify()
    assert set(r.all_scores.keys()) == set(Regime)


# ----------------------------------------------------------------------
# Input validation
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("spot", 0.0, "spot must be > 0"),
        ("spot", -1.0, "spot must be > 0"),
        ("max_pain", 0.0, "max_pain must be > 0"),
        ("iv_rank", -0.01, "iv_rank must be in"),
        ("iv_rank", 1.01, "iv_rank must be in"),
        ("iv_percentile", -0.01, "iv_percentile must be in"),
        ("iv_percentile", 2.0, "iv_percentile must be in"),
        ("hv_30", -0.01, "hv_30 must be >= 0"),
        ("expected_move_pct", -0.01, "expected_move_pct must be >= 0"),
        ("pcr_volume", -0.5, "pcr_volume must be >= 0"),
        ("pcr_oi", -0.5, "pcr_oi must be >= 0"),
        ("trend_strength", -0.01, "trend_strength must be in"),
        ("trend_strength", 1.5, "trend_strength must be in"),
        ("realized_vs_implied", -0.01, "realized_vs_implied must be >= 0"),
        ("breakout_signal", -0.01, "breakout_signal must be in"),
        ("breakout_signal", 1.01, "breakout_signal must be in"),
        ("oi_concentration_at_max_pain", -0.01, "oi_concentration_at_max_pain"),
        ("oi_concentration_at_max_pain", 1.5, "oi_concentration_at_max_pain"),
        ("days_to_next_event", -1, "days_to_next_event"),
        ("days_since_event", -1, "days_since_event"),
        ("days_to_nearest_opex", -1, "days_to_nearest_opex"),
        ("iv_rank_change_1d", -1.5, "iv_rank_change_1d"),
        ("iv_rank_change_1d", 1.5, "iv_rank_change_1d"),
    ],
)
def test_classify_input_validation_raises(
    field: str, value: Any, match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        _classify(**{field: value})


# ----------------------------------------------------------------------
# Property tests
# ----------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(
    iv_rank=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    iv_percentile=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    hv_30=st.floats(min_value=0.0, max_value=2.0, allow_nan=False),
    expected_move_pct=st.floats(min_value=0.0, max_value=0.5, allow_nan=False),
    pcr_volume=st.floats(min_value=0.0, max_value=10.0, allow_nan=False),
    pcr_oi=st.floats(min_value=0.0, max_value=10.0, allow_nan=False),
    trend_strength=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    realized_vs_implied=st.floats(min_value=0.0, max_value=5.0, allow_nan=False),
    breakout_signal=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    oi_concentration_at_max_pain=st.floats(
        min_value=0.0, max_value=1.0, allow_nan=False
    ),
    days_to_next_event=st.one_of(st.none(), st.integers(min_value=0, max_value=120)),
    days_since_event=st.one_of(st.none(), st.integers(min_value=0, max_value=120)),
    days_to_nearest_opex=st.one_of(st.none(), st.integers(min_value=0, max_value=120)),
    iv_rank_change_1d=st.one_of(
        st.none(), st.floats(min_value=-1.0, max_value=1.0, allow_nan=False)
    ),
    gap_pct=st.one_of(
        st.none(), st.floats(min_value=-1.0, max_value=1.0, allow_nan=False)
    ),
)
def test_classify_always_returns_valid_result(
    iv_rank: float,
    iv_percentile: float,
    hv_30: float,
    expected_move_pct: float,
    pcr_volume: float,
    pcr_oi: float,
    trend_strength: float,
    realized_vs_implied: float,
    breakout_signal: float,
    oi_concentration_at_max_pain: float,
    days_to_next_event: int | None,
    days_since_event: int | None,
    days_to_nearest_opex: int | None,
    iv_rank_change_1d: float | None,
    gap_pct: float | None,
) -> None:
    r = classify(
        spot=100.0,
        iv_rank=iv_rank,
        iv_percentile=iv_percentile,
        hv_30=hv_30,
        expected_move_pct=expected_move_pct,
        max_pain=100.0,
        pcr_volume=pcr_volume,
        pcr_oi=pcr_oi,
        days_to_next_event=days_to_next_event,
        next_event_kind=None,
        trend_strength=trend_strength,
        realized_vs_implied=realized_vs_implied,
        days_since_event=days_since_event,
        days_to_nearest_opex=days_to_nearest_opex,
        iv_rank_change_1d=iv_rank_change_1d,
        gap_pct=gap_pct,
        breakout_signal=breakout_signal,
        oi_concentration_at_max_pain=oi_concentration_at_max_pain,
    )
    assert isinstance(r, MarketStateResult)
    assert r.regime in set(Regime)
    assert 0.0 <= r.regime_score <= 1.0
    assert set(r.all_scores.keys()) == set(Regime)
    for s in r.all_scores.values():
        assert 0.0 <= s <= 1.0
    assert r.regime_score == pytest.approx(r.all_scores[r.regime], abs=1e-12)
    assert isinstance(r.tags, tuple)
