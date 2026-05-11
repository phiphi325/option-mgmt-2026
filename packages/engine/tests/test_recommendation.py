"""Recommendation Engine tests (M1.7).

Per plan v1.2 §17 M1.7 acceptance and §9.4.

Test discipline (mirrors M1.4 / M1.5b / M1.6 patterns):
- Direct fixture-based assertions on action × regime × profile mapping
- Hand-computed composite confidence checks
- Warning generation per individual trigger
- Hypothesis property tests for bounded outputs and determinism
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from engine.flow_score.types import Bias, FlowScore, RecommendedAction
from engine.market_state.classify import MarketStateResult
from engine.profiles import IncomeNeed, RiskTolerance, UserStrategyProfile
from engine.recommendation import (
    Recommendation,
    StrategyClass,
    build_warnings,
    recommend,
    render_rationale,
)
from engine.recommendation.warnings import (
    BORDERLINE_SCORE_BAND,
    EVENT_WINDOW_DAYS,
    GAMMA_AMPLIFIER_MAGNITUDE,
    LOW_CONFIDENCE_THRESHOLD,
    OPEX_PROXIMITY_DAYS,
)
from engine.regimes import Regime

# ----------------------------------------------------------------------
# helpers — build minimal valid upstream results
# ----------------------------------------------------------------------


def _flow_score(
    *,
    action: RecommendedAction = RecommendedAction.SELL_CALL_AGGRESSIVE,
    bias: Bias = Bias.BULLISH,
    score: float = 46.0,
    confidence: float = 0.50,
    gamma_sign: int = 0,
    gamma_risk: float = 0.20,
    pin_probability: float = 0.10,
) -> FlowScore:
    return FlowScore(
        score=score,
        bullish_score=max(score, 0.0),
        bearish_score=max(-score, 0.0),
        bias=bias,
        recommended_action=action,
        pin_probability=pin_probability,
        gamma_risk=gamma_risk,
        gamma_sign=gamma_sign,
        confidence=confidence,
        explanation="(test fixture explanation)",
        breakdown={},
    )


def _market_state(
    *,
    regime: Regime = Regime.LOW_IV_RANGE,
    regime_score: float = 0.60,
    iv_rank: float = 0.55,
    days_to_next_event: int | None = None,
    next_event_kind: str | None = None,
    days_to_nearest_opex: int | None = None,
) -> MarketStateResult:
    """Build a MarketStateResult with only the fields recommend() reads."""
    return MarketStateResult(
        regime=regime,
        regime_score=regime_score,
        all_scores={r: 0.0 for r in Regime},
        tags=(),
        spot=100.0,
        iv_rank=iv_rank,
        iv_percentile=0.5,
        hv_30=0.20,
        expected_move_pct=0.05,
        max_pain=100.0,
        max_pain_delta_pct=0.0,
        pcr_volume=0.5,
        pcr_oi=0.5,
        trend_strength=0.3,
        realized_vs_implied=1.0,
        breakout_signal=0.0,
        oi_concentration_at_max_pain=0.2,
        days_to_next_event=days_to_next_event,
        next_event_kind=next_event_kind,
        days_since_event=None,
        days_to_nearest_opex=days_to_nearest_opex,
        iv_rank_change_1d=None,
        gap_pct=None,
    )


def _user_profile(
    *,
    risk_tolerance: RiskTolerance = RiskTolerance.MODERATE,
    income_need: IncomeNeed = IncomeNeed.MEDIUM,
    min_iv_rank: int = 30,
    prefer_collars: bool = False,
) -> UserStrategyProfile:
    return UserStrategyProfile(
        risk_tolerance=risk_tolerance,
        income_need=income_need,
        max_position_pct=0.50,
        max_coverage_pct=0.75,
        min_iv_rank_for_short_premium=min_iv_rank,
        prefer_collars_over_covered_calls=prefer_collars,
    )


# ----------------------------------------------------------------------
# Base mapping: RecommendedAction → StrategyClass (no overrides)
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("action", "expected_strategy"),
    [
        (RecommendedAction.SELL_CALL_AGGRESSIVE, StrategyClass.COVERED_CALL_AGGRESSIVE),
        (RecommendedAction.SELL_CALL_PARTIAL, StrategyClass.COVERED_CALL_PARTIAL),
        (RecommendedAction.BUY_PROTECTION, StrategyClass.PROTECTIVE_PUT),
        (RecommendedAction.REDUCE_COVERAGE, StrategyClass.REDUCE_CALL_COVERAGE),
        (RecommendedAction.WAIT, StrategyClass.WAIT),
        (RecommendedAction.MONITOR, StrategyClass.MONITOR),
    ],
)
def test_base_action_to_strategy_mapping(
    action: RecommendedAction, expected_strategy: StrategyClass
) -> None:
    """In a benign regime (LOW_IV_RANGE) with a default profile, each
    `RecommendedAction` should map to its natural `StrategyClass`.
    """
    rec = recommend(
        market_state=_market_state(),
        flow_score=_flow_score(action=action),
        user_profile=_user_profile(),
    )
    assert rec.strategy_class is expected_strategy
    assert rec.action is action


# ----------------------------------------------------------------------
# Regime overrides
# ----------------------------------------------------------------------


def test_high_iv_event_downgrades_aggressive_to_partial() -> None:
    """HIGH_IV_EVENT regime → AGGRESSIVE call sale becomes PARTIAL."""
    rec = recommend(
        market_state=_market_state(regime=Regime.HIGH_IV_EVENT, days_to_next_event=3, next_event_kind="earnings"),
        flow_score=_flow_score(action=RecommendedAction.SELL_CALL_AGGRESSIVE),
        user_profile=_user_profile(),
    )
    assert rec.strategy_class is StrategyClass.COVERED_CALL_PARTIAL
    # The rationale should explain the downgrade
    assert "Event-elevated IV" in rec.rationale
    assert "adjusted from COVERED_CALL_AGGRESSIVE" in rec.rationale


def test_high_iv_pin_forces_wait_on_aggressive() -> None:
    """HIGH_IV_PIN regime → AGGRESSIVE call sale becomes WAIT."""
    rec = recommend(
        market_state=_market_state(regime=Regime.HIGH_IV_PIN, days_to_nearest_opex=2),
        flow_score=_flow_score(action=RecommendedAction.SELL_CALL_AGGRESSIVE),
        user_profile=_user_profile(),
    )
    assert rec.strategy_class is StrategyClass.WAIT
    assert "Pin-risk regime" in rec.rationale


def test_high_iv_pin_forces_wait_on_partial() -> None:
    """HIGH_IV_PIN regime → PARTIAL call sale also becomes WAIT."""
    rec = recommend(
        market_state=_market_state(regime=Regime.HIGH_IV_PIN),
        flow_score=_flow_score(action=RecommendedAction.SELL_CALL_PARTIAL),
        user_profile=_user_profile(),
    )
    assert rec.strategy_class is StrategyClass.WAIT


def test_low_iv_trend_downgrades_aggressive() -> None:
    rec = recommend(
        market_state=_market_state(regime=Regime.LOW_IV_TREND),
        flow_score=_flow_score(action=RecommendedAction.SELL_CALL_AGGRESSIVE),
        user_profile=_user_profile(),
    )
    assert rec.strategy_class is StrategyClass.COVERED_CALL_PARTIAL
    assert "Low-IV trend" in rec.rationale


def test_breakout_downgrades_aggressive() -> None:
    rec = recommend(
        market_state=_market_state(regime=Regime.BREAKOUT),
        flow_score=_flow_score(action=RecommendedAction.SELL_CALL_AGGRESSIVE),
        user_profile=_user_profile(),
    )
    assert rec.strategy_class is StrategyClass.COVERED_CALL_PARTIAL
    assert "Breakout" in rec.rationale


def test_post_event_reprice_forces_monitor_on_aggressive() -> None:
    rec = recommend(
        market_state=_market_state(regime=Regime.POST_EVENT_REPRICE),
        flow_score=_flow_score(action=RecommendedAction.SELL_CALL_AGGRESSIVE),
        user_profile=_user_profile(),
    )
    assert rec.strategy_class is StrategyClass.MONITOR
    assert "Post-event reprice" in rec.rationale


def test_low_iv_range_preserves_aggressive() -> None:
    """LOW_IV_RANGE is the 'clean' regime — no downgrade applied."""
    rec = recommend(
        market_state=_market_state(regime=Regime.LOW_IV_RANGE),
        flow_score=_flow_score(action=RecommendedAction.SELL_CALL_AGGRESSIVE),
        user_profile=_user_profile(),
    )
    assert rec.strategy_class is StrategyClass.COVERED_CALL_AGGRESSIVE
    assert "adjusted from" not in rec.rationale


def test_buy_protection_with_collar_preference() -> None:
    """BUY_PROTECTION + prefer_collars=True → COLLAR (not PROTECTIVE_PUT)."""
    rec = recommend(
        market_state=_market_state(),
        flow_score=_flow_score(action=RecommendedAction.BUY_PROTECTION, score=-30.0, bias=Bias.BEARISH),
        user_profile=_user_profile(prefer_collars=True),
    )
    assert rec.strategy_class is StrategyClass.COLLAR
    assert "Profile prefers collars" in rec.rationale


def test_buy_protection_without_collar_preference() -> None:
    rec = recommend(
        market_state=_market_state(),
        flow_score=_flow_score(action=RecommendedAction.BUY_PROTECTION, score=-30.0, bias=Bias.BEARISH),
        user_profile=_user_profile(prefer_collars=False),
    )
    assert rec.strategy_class is StrategyClass.PROTECTIVE_PUT


# ----------------------------------------------------------------------
# Profile overrides
# ----------------------------------------------------------------------


def test_conservative_profile_downgrades_aggressive_to_partial() -> None:
    """Conservative risk tolerance → AGGRESSIVE → PARTIAL."""
    rec = recommend(
        market_state=_market_state(regime=Regime.LOW_IV_RANGE),  # no regime downgrade
        flow_score=_flow_score(action=RecommendedAction.SELL_CALL_AGGRESSIVE),
        user_profile=_user_profile(risk_tolerance=RiskTolerance.CONSERVATIVE),
    )
    assert rec.strategy_class is StrategyClass.COVERED_CALL_PARTIAL
    assert "Conservative profile" in rec.rationale


def test_aggressive_profile_preserves_aggressive() -> None:
    rec = recommend(
        market_state=_market_state(regime=Regime.LOW_IV_RANGE),
        flow_score=_flow_score(action=RecommendedAction.SELL_CALL_AGGRESSIVE),
        user_profile=_user_profile(risk_tolerance=RiskTolerance.AGGRESSIVE),
    )
    assert rec.strategy_class is StrategyClass.COVERED_CALL_AGGRESSIVE


def test_moderate_profile_preserves_aggressive() -> None:
    rec = recommend(
        market_state=_market_state(regime=Regime.LOW_IV_RANGE),
        flow_score=_flow_score(action=RecommendedAction.SELL_CALL_AGGRESSIVE),
        user_profile=_user_profile(risk_tolerance=RiskTolerance.MODERATE),
    )
    assert rec.strategy_class is StrategyClass.COVERED_CALL_AGGRESSIVE


# ----------------------------------------------------------------------
# IV-rank gate
# ----------------------------------------------------------------------


def test_iv_rank_gate_vetoes_aggressive() -> None:
    """IV rank below user threshold → short-premium → MONITOR."""
    rec = recommend(
        market_state=_market_state(regime=Regime.LOW_IV_RANGE, iv_rank=0.20),  # 20%
        flow_score=_flow_score(action=RecommendedAction.SELL_CALL_AGGRESSIVE),
        user_profile=_user_profile(min_iv_rank=50),  # threshold 50%
    )
    assert rec.strategy_class is StrategyClass.MONITOR
    assert "IV rank below" in rec.rationale


def test_iv_rank_gate_does_not_affect_protective_actions() -> None:
    """IV rank gate is only for SHORT-premium actions; BUY_PROTECTION is unaffected."""
    rec = recommend(
        market_state=_market_state(regime=Regime.LOW_IV_RANGE, iv_rank=0.10),  # very low
        flow_score=_flow_score(action=RecommendedAction.BUY_PROTECTION, score=-30.0, bias=Bias.BEARISH),
        user_profile=_user_profile(min_iv_rank=50),
    )
    assert rec.strategy_class is StrategyClass.PROTECTIVE_PUT  # unaffected


def test_iv_rank_at_threshold_no_gate() -> None:
    """IV rank exactly equal to threshold → gate does NOT fire (strict less-than)."""
    rec = recommend(
        market_state=_market_state(regime=Regime.LOW_IV_RANGE, iv_rank=0.50),
        flow_score=_flow_score(action=RecommendedAction.SELL_CALL_AGGRESSIVE),
        user_profile=_user_profile(min_iv_rank=50),
    )
    assert rec.strategy_class is StrategyClass.COVERED_CALL_AGGRESSIVE  # preserved


# ----------------------------------------------------------------------
# Confidence composition (V1: flow × regime)
# ----------------------------------------------------------------------


def test_confidence_is_flow_times_regime_score() -> None:
    flow = _flow_score(confidence=0.40)
    ms = _market_state(regime_score=0.60)
    rec = recommend(market_state=ms, flow_score=flow, user_profile=_user_profile())
    assert rec.confidence == pytest.approx(0.40 * 0.60, abs=1e-12)


def test_confidence_clipped_at_one() -> None:
    """Even with both factors at maximum, confidence stays in [0, 1]."""
    flow = _flow_score(confidence=1.0)
    ms = _market_state(regime_score=1.0)
    rec = recommend(market_state=ms, flow_score=flow, user_profile=_user_profile())
    assert rec.confidence == 1.0
    assert rec.confidence <= 1.0


def test_confidence_zero_when_either_factor_zero() -> None:
    flow_zero = _flow_score(confidence=0.0)
    ms_high = _market_state(regime_score=1.0)
    rec_a = recommend(market_state=ms_high, flow_score=flow_zero, user_profile=_user_profile())
    assert rec_a.confidence == 0.0

    flow_high = _flow_score(confidence=1.0)
    ms_zero = _market_state(regime_score=0.0)
    rec_b = recommend(market_state=ms_zero, flow_score=flow_high, user_profile=_user_profile())
    assert rec_b.confidence == 0.0


# ----------------------------------------------------------------------
# Parameters dict
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("strategy_action", "expected_keys"),
    [
        (RecommendedAction.SELL_CALL_AGGRESSIVE, {"target_dte", "target_delta", "size_pct", "urgency_days"}),
        (RecommendedAction.SELL_CALL_PARTIAL, {"target_dte", "target_delta", "size_pct", "urgency_days"}),
        (RecommendedAction.BUY_PROTECTION, {"target_dte", "target_delta", "size_pct", "urgency_days"}),
        (RecommendedAction.REDUCE_COVERAGE, {"target_dte", "target_delta", "size_pct", "urgency_days"}),
        (RecommendedAction.WAIT, set()),
        (RecommendedAction.MONITOR, set()),
    ],
)
def test_parameters_keys_per_strategy(
    strategy_action: RecommendedAction, expected_keys: set[str]
) -> None:
    rec = recommend(
        market_state=_market_state(),
        flow_score=_flow_score(action=strategy_action),
        user_profile=_user_profile(),
    )
    assert set(rec.parameters.keys()) == expected_keys


def test_aggressive_parameters_have_smaller_delta_than_partial() -> None:
    """AGGRESSIVE = further OTM (smaller delta); PARTIAL = closer to ATM (bigger delta)."""
    rec_agg = recommend(
        market_state=_market_state(),
        flow_score=_flow_score(action=RecommendedAction.SELL_CALL_AGGRESSIVE),
        user_profile=_user_profile(),
    )
    rec_par = recommend(
        market_state=_market_state(),
        flow_score=_flow_score(action=RecommendedAction.SELL_CALL_PARTIAL),
        user_profile=_user_profile(),
    )
    assert rec_agg.parameters["target_delta"] < rec_par.parameters["target_delta"]


def test_aggressive_size_larger_than_partial() -> None:
    rec_agg = recommend(
        market_state=_market_state(),
        flow_score=_flow_score(action=RecommendedAction.SELL_CALL_AGGRESSIVE),
        user_profile=_user_profile(),
    )
    rec_par = recommend(
        market_state=_market_state(),
        flow_score=_flow_score(action=RecommendedAction.SELL_CALL_PARTIAL),
        user_profile=_user_profile(),
    )
    assert rec_agg.parameters["size_pct"] > rec_par.parameters["size_pct"]


def test_protective_put_is_fully_covered() -> None:
    rec = recommend(
        market_state=_market_state(),
        flow_score=_flow_score(action=RecommendedAction.BUY_PROTECTION, score=-30.0, bias=Bias.BEARISH),
        user_profile=_user_profile(),
    )
    assert rec.parameters["size_pct"] == 1.0


# ----------------------------------------------------------------------
# Warnings
# ----------------------------------------------------------------------


def test_warning_low_confidence() -> None:
    flow = _flow_score(confidence=0.05)  # well below threshold
    warns = build_warnings(market_state=_market_state(), flow_score=flow, user_profile=_user_profile())
    assert any("Low confidence" in w for w in warns)


def test_warning_low_confidence_threshold_boundary() -> None:
    """Confidence exactly at threshold does NOT trigger the warning."""
    flow_at = _flow_score(confidence=LOW_CONFIDENCE_THRESHOLD)
    warns = build_warnings(market_state=_market_state(), flow_score=flow_at, user_profile=_user_profile())
    assert not any("Low confidence" in w for w in warns)


def test_warning_event_window() -> None:
    ms = _market_state(days_to_next_event=5, next_event_kind="earnings")
    warns = build_warnings(market_state=ms, flow_score=_flow_score(), user_profile=_user_profile())
    assert any("Event window" in w and "earnings" in w for w in warns)


def test_warning_event_window_boundary_inclusive() -> None:
    """`days_to_next_event = 7` (the threshold) should trigger."""
    ms = _market_state(days_to_next_event=EVENT_WINDOW_DAYS, next_event_kind="fomc")
    warns = build_warnings(market_state=ms, flow_score=_flow_score(), user_profile=_user_profile())
    assert any("Event window" in w for w in warns)


def test_warning_event_window_beyond_threshold_silent() -> None:
    ms = _market_state(days_to_next_event=EVENT_WINDOW_DAYS + 1, next_event_kind="earnings")
    warns = build_warnings(market_state=ms, flow_score=_flow_score(), user_profile=_user_profile())
    assert not any("Event window" in w for w in warns)


def test_warning_opex_proximity() -> None:
    ms = _market_state(days_to_nearest_opex=2)
    warns = build_warnings(market_state=ms, flow_score=_flow_score(), user_profile=_user_profile())
    assert any("Opex proximity" in w for w in warns)


def test_warning_opex_threshold_inclusive() -> None:
    ms = _market_state(days_to_nearest_opex=OPEX_PROXIMITY_DAYS)
    warns = build_warnings(market_state=ms, flow_score=_flow_score(), user_profile=_user_profile())
    assert any("Opex proximity" in w for w in warns)


def test_warning_opex_negative_silent() -> None:
    """Past opex (negative) should NOT trigger."""
    ms = _market_state(days_to_nearest_opex=-1)
    warns = build_warnings(market_state=ms, flow_score=_flow_score(), user_profile=_user_profile())
    assert not any("Opex proximity" in w for w in warns)


def test_warning_gamma_amplifier() -> None:
    flow = _flow_score(gamma_sign=-1, gamma_risk=0.8)
    warns = build_warnings(market_state=_market_state(), flow_score=flow, user_profile=_user_profile())
    assert any("amplifier" in w for w in warns)


def test_warning_gamma_amplifier_silent_when_positive_sign() -> None:
    """Dealer net LONG gamma — no amplifier warning (they dampen vol)."""
    flow = _flow_score(gamma_sign=+1, gamma_risk=0.8)
    warns = build_warnings(market_state=_market_state(), flow_score=flow, user_profile=_user_profile())
    assert not any("amplifier" in w for w in warns)


def test_warning_gamma_amplifier_silent_when_below_magnitude() -> None:
    flow = _flow_score(gamma_sign=-1, gamma_risk=GAMMA_AMPLIFIER_MAGNITUDE - 0.1)
    warns = build_warnings(market_state=_market_state(), flow_score=flow, user_profile=_user_profile())
    assert not any("amplifier" in w for w in warns)


def test_warning_borderline_score() -> None:
    flow = _flow_score(score=10.0, action=RecommendedAction.SELL_CALL_PARTIAL)
    warns = build_warnings(market_state=_market_state(), flow_score=flow, user_profile=_user_profile())
    assert any("Borderline" in w for w in warns)


def test_warning_borderline_score_band_boundary() -> None:
    """|score| < BORDERLINE_SCORE_BAND triggers; equals does not."""
    flow_eq = _flow_score(score=BORDERLINE_SCORE_BAND, action=RecommendedAction.SELL_CALL_PARTIAL)
    warns_eq = build_warnings(market_state=_market_state(), flow_score=flow_eq, user_profile=_user_profile())
    assert not any("Borderline" in w for w in warns_eq)

    flow_under = _flow_score(score=BORDERLINE_SCORE_BAND - 0.1, action=RecommendedAction.SELL_CALL_PARTIAL)
    warns_under = build_warnings(market_state=_market_state(), flow_score=flow_under, user_profile=_user_profile())
    assert any("Borderline" in w for w in warns_under)


def test_warning_iv_rank_below_threshold_only_for_short_premium() -> None:
    """IV-rank-below warning only fires for SELL_CALL_AGGRESSIVE / SELL_CALL_PARTIAL."""
    # Sell action → fires
    flow_sell = _flow_score(action=RecommendedAction.SELL_CALL_AGGRESSIVE)
    warns_sell = build_warnings(
        market_state=_market_state(iv_rank=0.20),
        flow_score=flow_sell,
        user_profile=_user_profile(min_iv_rank=50),
    )
    assert any("below your short-premium threshold" in w for w in warns_sell)

    # Buy protection → silent
    flow_buy = _flow_score(action=RecommendedAction.BUY_PROTECTION, score=-30.0, bias=Bias.BEARISH)
    warns_buy = build_warnings(
        market_state=_market_state(iv_rank=0.20),
        flow_score=flow_buy,
        user_profile=_user_profile(min_iv_rank=50),
    )
    assert not any("below your short-premium threshold" in w for w in warns_buy)


def test_warnings_empty_on_benign_inputs() -> None:
    """Healthy chain → no warnings."""
    rec = recommend(
        market_state=_market_state(),  # benign defaults
        flow_score=_flow_score(confidence=0.50, score=46.0, gamma_sign=0),
        user_profile=_user_profile(min_iv_rank=30),
    )
    assert rec.warnings == ()


# ----------------------------------------------------------------------
# Rationale builder direct tests
# ----------------------------------------------------------------------


def test_rationale_includes_all_required_fields() -> None:
    text = render_rationale(
        strategy_class=StrategyClass.COVERED_CALL_AGGRESSIVE,
        market_state=_market_state(regime=Regime.LOW_IV_RANGE, regime_score=0.55),
        flow_score=_flow_score(score=46.2, bias=Bias.BULLISH, action=RecommendedAction.SELL_CALL_AGGRESSIVE),
    )
    assert "Recommended strategy: COVERED_CALL_AGGRESSIVE" in text
    assert "SELL_CALL_AGGRESSIVE per FlowScore §9.3a" in text
    assert "Market state: LOW_IV_RANGE" in text
    assert "regime score 0.55" in text
    assert "score +46.2" in text
    assert "bias BULLISH" in text


def test_rationale_with_downgrade() -> None:
    text = render_rationale(
        strategy_class=StrategyClass.COVERED_CALL_PARTIAL,
        market_state=_market_state(regime=Regime.HIGH_IV_EVENT),
        flow_score=_flow_score(action=RecommendedAction.SELL_CALL_AGGRESSIVE, score=46.2),
        downgrade_reason="Event-elevated IV — gamma/vega risk argues against aggressive premium sale",
        original_strategy=StrategyClass.COVERED_CALL_AGGRESSIVE,
    )
    assert "Event-elevated IV" in text
    assert "adjusted from COVERED_CALL_AGGRESSIVE" in text


def test_rationale_omits_downgrade_when_none() -> None:
    text = render_rationale(
        strategy_class=StrategyClass.COVERED_CALL_AGGRESSIVE,
        market_state=_market_state(),
        flow_score=_flow_score(),
    )
    assert "adjusted from" not in text


# ----------------------------------------------------------------------
# Determinism + shape
# ----------------------------------------------------------------------


def test_recommend_returns_full_shape() -> None:
    rec = recommend(
        market_state=_market_state(),
        flow_score=_flow_score(),
        user_profile=_user_profile(),
    )
    assert isinstance(rec, Recommendation)
    assert isinstance(rec.strategy_class, StrategyClass)
    assert isinstance(rec.action, RecommendedAction)
    assert isinstance(rec.regime, Regime)
    assert 0.0 <= rec.confidence <= 1.0
    assert isinstance(rec.rationale, str)
    assert len(rec.rationale) > 0
    assert isinstance(rec.warnings, tuple)
    assert isinstance(rec.parameters, dict)


def test_recommend_is_deterministic() -> None:
    """Same inputs → byte-equal output (pure function per ADR-0005)."""
    ms = _market_state()
    fs = _flow_score()
    up = _user_profile()
    rec_a = recommend(market_state=ms, flow_score=fs, user_profile=up)
    rec_b = recommend(market_state=ms, flow_score=fs, user_profile=up)
    assert rec_a == rec_b


def test_recommendation_is_frozen() -> None:
    """Frozen dataclass — assignment to fields raises FrozenInstanceError."""
    from dataclasses import FrozenInstanceError

    rec = recommend(
        market_state=_market_state(),
        flow_score=_flow_score(),
        user_profile=_user_profile(),
    )
    with pytest.raises(FrozenInstanceError):
        rec.confidence = 0.5  # type: ignore[misc]


# ----------------------------------------------------------------------
# Hypothesis property tests
# ----------------------------------------------------------------------


@given(
    confidence=st.floats(min_value=0.0, max_value=1.0),
    regime_score=st.floats(min_value=0.0, max_value=1.0),
    score=st.floats(min_value=-100.0, max_value=100.0),
    iv_rank=st.floats(min_value=0.0, max_value=1.0),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_confidence_in_unit_interval(
    confidence: float, regime_score: float, score: float, iv_rank: float
) -> None:
    """For any valid input, composite confidence is in [0, 1]."""
    rec = recommend(
        market_state=_market_state(regime_score=regime_score, iv_rank=iv_rank),
        flow_score=_flow_score(confidence=confidence, score=score),
        user_profile=_user_profile(),
    )
    assert 0.0 <= rec.confidence <= 1.0


@given(
    action=st.sampled_from(RecommendedAction),
    regime=st.sampled_from(Regime),
    risk=st.sampled_from(RiskTolerance),
    prefer_collars=st.booleans(),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_strategy_class_is_valid_enum(
    action: RecommendedAction,
    regime: Regime,
    risk: RiskTolerance,
    prefer_collars: bool,
) -> None:
    """Across the full Cartesian product of inputs, the returned
    `strategy_class` is always a member of `StrategyClass`.
    """
    rec = recommend(
        market_state=_market_state(regime=regime),
        flow_score=_flow_score(action=action),
        user_profile=_user_profile(risk_tolerance=risk, prefer_collars=prefer_collars),
    )
    assert rec.strategy_class in set(StrategyClass)


@given(
    confidence=st.floats(min_value=0.0, max_value=1.0),
    regime_score=st.floats(min_value=0.0, max_value=1.0),
)
@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_confidence_equals_product(
    confidence: float, regime_score: float
) -> None:
    """Composite confidence is exactly the product of flow + regime confidences."""
    rec = recommend(
        market_state=_market_state(regime_score=regime_score),
        flow_score=_flow_score(confidence=confidence),
        user_profile=_user_profile(),
    )
    assert rec.confidence == pytest.approx(confidence * regime_score, abs=1e-12)
