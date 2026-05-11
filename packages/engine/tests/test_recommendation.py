"""Recommendation Engine V1 tests (M1.9, plan-true).

Per plan v1.2 §17 M1.8 + M1.9 acceptance, §9.5, and §22.8.

Test discipline:
- Direct fixture-based assertions on each of the 8 V1 rules firing
- YAML loader validation: malformed YAML, unknown clauses, bad emit
- Predicate evaluator clause-by-clause
- Regime whitelist + first-match-wins ordering
- Hypothesis property tests for bounded confidence + determinism
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from engine.flow_score.types import Bias, FlowScore, RecommendedAction
from engine.market_state.classify import MarketStateResult
from engine.profiles import IncomeNeed, ProfileStyle, RiskTolerance, UserStrategyProfile
from engine.recommendation import (
    EmittedAction,
    EvaluationContext,
    PositionState,
    RecommendationResult,
    RuleSpec,
    evaluate_clause,
    is_emit_in_regime_whitelist,
    load_rules_yaml,
    matches,
    recommend,
    select_winning_rule,
    supported_clauses,
)
from engine.recommendation.yaml_loader import _parse_rules_text
from engine.regimes import Regime

# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------


_PACKAGED_RULES_PATH = Path(__file__).resolve().parent.parent / "config" / "rules.yaml"


def _flow_score(
    *,
    action: RecommendedAction = RecommendedAction.MONITOR,
    bias: Bias = Bias.NEUTRAL,
    score: float = 0.0,
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
    iv_rank_change_1d: float | None = 0.0,
    days_to_next_event: int | None = None,
    next_event_kind: str | None = None,
    days_since_event: int | None = None,
    days_to_nearest_opex: int | None = None,
    spot: float = 100.0,
) -> MarketStateResult:
    return MarketStateResult(
        regime=regime,
        regime_score=regime_score,
        all_scores={r: 0.0 for r in Regime},
        tags=(),
        spot=spot,
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
        days_since_event=days_since_event,
        days_to_nearest_opex=days_to_nearest_opex,
        iv_rank_change_1d=iv_rank_change_1d,
        gap_pct=None,
    )


def _user_profile(
    *,
    risk_tolerance: RiskTolerance = RiskTolerance.MODERATE,
    income_need: IncomeNeed = IncomeNeed.MEDIUM,
    min_iv_rank: int = 30,
    prefer_collars: bool = False,
    drawdown_tolerance: float = 0.15,
    style: ProfileStyle = ProfileStyle.BALANCED,
) -> UserStrategyProfile:
    return UserStrategyProfile(
        risk_tolerance=risk_tolerance,
        income_need=income_need,
        max_position_pct=0.50,
        max_coverage_pct=0.75,
        min_iv_rank_for_short_premium=min_iv_rank,
        prefer_collars_over_covered_calls=prefer_collars,
        drawdown_tolerance=drawdown_tolerance,
        style=style,
    )


def _positions(**kwargs: object) -> PositionState:
    return PositionState(**kwargs)  # type: ignore[arg-type]


@pytest.fixture(scope="module")
def packaged_rules() -> tuple[RuleSpec, ...]:
    """Load the 8 V1 rules from the packaged config/rules.yaml."""
    return load_rules_yaml(_PACKAGED_RULES_PATH)


# ----------------------------------------------------------------------
# YAML loader
# ----------------------------------------------------------------------


def test_load_default_rules_returns_eight(packaged_rules: tuple[RuleSpec, ...]) -> None:
    """The packaged rules.yaml has exactly the 8 V1 rules per §22.8."""
    assert len(packaged_rules) == 8


def test_load_default_rules_ids(packaged_rules: tuple[RuleSpec, ...]) -> None:
    expected = {
        "high_iv_sell_call",
        "roll_up_and_out_when_short_call_threatened",
        "reduce_coverage_on_breakout_post_event",
        "open_collar_pre_event",
        "buy_long_dated_put_low_iv_trend",
        "monetize_put_on_breakout",
        "wheel_on_low_iv_range",
        "hold_no_op",
    }
    assert {r.id for r in packaged_rules} == expected


def test_load_default_rules_emits(packaged_rules: tuple[RuleSpec, ...]) -> None:
    """Every loaded rule emits a valid EmittedAction."""
    for r in packaged_rules:
        assert isinstance(r.emit, EmittedAction)


def test_load_rules_yaml_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_rules_yaml(Path("/nonexistent/rules.yaml"))


def test_parse_rules_empty_yaml_raises() -> None:
    with pytest.raises(ValueError, match="empty"):
        _parse_rules_text("", source="<test>")


def test_parse_rules_not_a_list_raises() -> None:
    with pytest.raises(ValueError, match="top level must be a list"):
        _parse_rules_text("foo: bar\n", source="<test>")


def test_parse_rules_missing_required_field() -> None:
    with pytest.raises(ValueError, match="missing required fields"):
        _parse_rules_text(
            "- id: x\n  when: {}\n  emit: NO_OP\n", source="<test>"
        )  # missing rationale


def test_parse_rules_bad_emit() -> None:
    with pytest.raises(ValueError, match="invalid emit"):
        _parse_rules_text(
            "- id: x\n"
            "  when: {}\n"
            "  emit: NOT_A_REAL_ACTION\n"
            "  rationale: foo\n",
            source="<test>",
        )


def test_parse_rules_unsupported_clause() -> None:
    with pytest.raises(ValueError, match="unsupported clauses"):
        _parse_rules_text(
            "- id: x\n"
            "  when: { not_a_real_clause: 5 }\n"
            "  emit: NO_OP\n"
            "  rationale: foo\n",
            source="<test>",
        )


def test_parse_rules_when_not_mapping() -> None:
    with pytest.raises(ValueError, match="invalid 'when' block"):
        _parse_rules_text(
            "- id: x\n"
            "  when: [a, b]\n"
            "  emit: NO_OP\n"
            "  rationale: foo\n",
            source="<test>",
        )


def test_parse_rules_risks_not_list() -> None:
    with pytest.raises(ValueError, match="must be a list"):
        _parse_rules_text(
            "- id: x\n"
            "  when: {}\n"
            "  emit: NO_OP\n"
            "  rationale: foo\n"
            "  risks: not_a_list\n",
            source="<test>",
        )


# ----------------------------------------------------------------------
# Clause evaluator
# ----------------------------------------------------------------------


def test_supported_clauses_count() -> None:
    """All 15 documented clause keys are supported."""
    sup = supported_clauses()
    expected = {
        "confidence_lte",
        "days_since_event_lte",
        "days_to_expiry_lte",
        "days_to_next_event_lte",
        "drawdown_tolerance_lte",
        "has_long_put",
        "has_short_call",
        "has_short_call_within_pct",
        "has_short_put",
        "iv_rank_change_1d_lte",
        "iv_rank_gte",
        "iv_rank_lte",
        "profile_style",
        "put_pnl_pct_gte",
        "regime",
    }
    assert sup == expected


def _ctx(
    *,
    market_state: MarketStateResult | None = None,
    flow_score: FlowScore | None = None,
    positions: PositionState | None = None,
    profile: UserStrategyProfile | None = None,
    confidence: float = 0.50,
) -> EvaluationContext:
    return EvaluationContext(
        market_state=market_state or _market_state(),
        flow_score=flow_score or _flow_score(),
        positions=positions or _positions(),
        profile=profile or _user_profile(),
        confidence=confidence,
    )


def test_clause_regime_string() -> None:
    ctx = _ctx(market_state=_market_state(regime=Regime.HIGH_IV_EVENT))
    assert evaluate_clause(key="regime", value="HIGH_IV_EVENT", ctx=ctx) is True
    assert evaluate_clause(key="regime", value="LOW_IV_RANGE", ctx=ctx) is False


def test_clause_regime_list() -> None:
    ctx = _ctx(market_state=_market_state(regime=Regime.LOW_IV_RANGE))
    assert (
        evaluate_clause(
            key="regime", value=["HIGH_IV_EVENT", "LOW_IV_RANGE"], ctx=ctx
        )
        is True
    )
    assert (
        evaluate_clause(key="regime", value=["BREAKOUT", "LOW_IV_TREND"], ctx=ctx)
        is False
    )


def test_clause_iv_rank_gte() -> None:
    ctx = _ctx(market_state=_market_state(iv_rank=0.65))
    assert evaluate_clause(key="iv_rank_gte", value=50, ctx=ctx) is True
    assert evaluate_clause(key="iv_rank_gte", value=70, ctx=ctx) is False


def test_clause_iv_rank_lte() -> None:
    ctx = _ctx(market_state=_market_state(iv_rank=0.25))
    assert evaluate_clause(key="iv_rank_lte", value=30, ctx=ctx) is True
    assert evaluate_clause(key="iv_rank_lte", value=20, ctx=ctx) is False


def test_clause_iv_rank_change_1d_lte() -> None:
    ctx = _ctx(market_state=_market_state(iv_rank_change_1d=-0.20))
    assert evaluate_clause(key="iv_rank_change_1d_lte", value=-15, ctx=ctx) is True
    ctx2 = _ctx(market_state=_market_state(iv_rank_change_1d=0.05))
    assert evaluate_clause(key="iv_rank_change_1d_lte", value=-15, ctx=ctx2) is False


def test_clause_iv_rank_change_1d_lte_none_means_false() -> None:
    ctx = _ctx(market_state=_market_state(iv_rank_change_1d=None))
    assert evaluate_clause(key="iv_rank_change_1d_lte", value=-15, ctx=ctx) is False


def test_clause_days_to_next_event_lte() -> None:
    ctx = _ctx(market_state=_market_state(days_to_next_event=5))
    assert evaluate_clause(key="days_to_next_event_lte", value=7, ctx=ctx) is True
    assert evaluate_clause(key="days_to_next_event_lte", value=3, ctx=ctx) is False


def test_clause_days_to_next_event_lte_none_means_false() -> None:
    ctx = _ctx(market_state=_market_state(days_to_next_event=None))
    assert evaluate_clause(key="days_to_next_event_lte", value=7, ctx=ctx) is False


def test_clause_days_since_event_lte() -> None:
    ctx = _ctx(market_state=_market_state(days_since_event=1))
    assert evaluate_clause(key="days_since_event_lte", value=2, ctx=ctx) is True


def test_clause_has_short_call() -> None:
    ctx = _ctx(positions=_positions(has_short_call=True))
    assert evaluate_clause(key="has_short_call", value=True, ctx=ctx) is True
    assert evaluate_clause(key="has_short_call", value=False, ctx=ctx) is False


def test_clause_has_short_call_within_pct() -> None:
    """Short call at K=101 vs spot=100 → within 1.5%, but not within 0.5%."""
    ctx = _ctx(
        market_state=_market_state(spot=100.0),
        positions=_positions(has_short_call=True, nearest_short_call_strike=101.0),
    )
    assert (
        evaluate_clause(key="has_short_call_within_pct", value=1.5, ctx=ctx) is True
    )
    assert (
        evaluate_clause(key="has_short_call_within_pct", value=0.5, ctx=ctx) is False
    )


def test_clause_has_short_call_within_pct_no_short_call() -> None:
    ctx = _ctx(positions=_positions(has_short_call=False))
    assert (
        evaluate_clause(key="has_short_call_within_pct", value=1.5, ctx=ctx) is False
    )


def test_clause_has_long_put() -> None:
    ctx = _ctx(positions=_positions(has_long_put=True))
    assert evaluate_clause(key="has_long_put", value=True, ctx=ctx) is True
    assert evaluate_clause(key="has_long_put", value=False, ctx=ctx) is False


def test_clause_has_short_put() -> None:
    ctx = _ctx(positions=_positions(has_short_put=True))
    assert evaluate_clause(key="has_short_put", value=True, ctx=ctx) is True


def test_clause_days_to_expiry_lte() -> None:
    ctx = _ctx(
        positions=_positions(has_short_call=True, nearest_short_call_dte=10)
    )
    assert evaluate_clause(key="days_to_expiry_lte", value=14, ctx=ctx) is True
    assert evaluate_clause(key="days_to_expiry_lte", value=5, ctx=ctx) is False


def test_clause_put_pnl_pct_gte() -> None:
    ctx = _ctx(positions=_positions(has_long_put=True, long_put_pnl_pct=0.40))
    assert evaluate_clause(key="put_pnl_pct_gte", value=0.30, ctx=ctx) is True
    assert evaluate_clause(key="put_pnl_pct_gte", value=0.50, ctx=ctx) is False


def test_clause_put_pnl_pct_gte_no_put() -> None:
    ctx = _ctx(positions=_positions(has_long_put=False, long_put_pnl_pct=0.40))
    assert evaluate_clause(key="put_pnl_pct_gte", value=0.30, ctx=ctx) is False


def test_clause_drawdown_tolerance_lte() -> None:
    ctx = _ctx(profile=_user_profile(drawdown_tolerance=0.15))
    assert evaluate_clause(key="drawdown_tolerance_lte", value=0.20, ctx=ctx) is True
    assert evaluate_clause(key="drawdown_tolerance_lte", value=0.10, ctx=ctx) is False


def test_clause_profile_style() -> None:
    ctx = _ctx(profile=_user_profile(style=ProfileStyle.INCOME))
    assert evaluate_clause(key="profile_style", value="income", ctx=ctx) is True
    assert evaluate_clause(key="profile_style", value="growth", ctx=ctx) is False


def test_clause_confidence_lte() -> None:
    ctx = _ctx(confidence=0.25)
    assert evaluate_clause(key="confidence_lte", value=0.30, ctx=ctx) is True
    assert evaluate_clause(key="confidence_lte", value=0.20, ctx=ctx) is False


def test_clause_unknown_raises() -> None:
    ctx = _ctx()
    with pytest.raises(ValueError, match="Unknown rule clause"):
        evaluate_clause(key="not_a_real_clause", value=0, ctx=ctx)


# ----------------------------------------------------------------------
# Regime whitelist
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("regime", "emit", "expected"),
    [
        (Regime.HIGH_IV_EVENT, EmittedAction.OPEN_COLLAR, True),
        (Regime.HIGH_IV_EVENT, EmittedAction.SELL_COVERED_CALL_PARTIAL, True),
        (Regime.HIGH_IV_EVENT, EmittedAction.MONETIZE_PUT, False),
        (Regime.LOW_IV_RANGE, EmittedAction.SELL_COVERED_CALL_PARTIAL, True),
        (Regime.LOW_IV_RANGE, EmittedAction.WHEEL_SHORT_PUT, True),
        (Regime.LOW_IV_RANGE, EmittedAction.BUY_LONG_DATED_PUT, False),
        (Regime.LOW_IV_TREND, EmittedAction.BUY_LONG_DATED_PUT, True),
        (Regime.BREAKOUT, EmittedAction.ROLL_UP_AND_OUT, True),
        (Regime.BREAKOUT, EmittedAction.MONETIZE_PUT, True),
        # NO_OP always allowed (fallback)
        (Regime.HIGH_IV_EVENT, EmittedAction.NO_OP, True),
        (Regime.LOW_IV_RANGE, EmittedAction.NO_OP, True),
    ],
)
def test_regime_whitelist(
    regime: Regime, emit: EmittedAction, expected: bool
) -> None:
    assert is_emit_in_regime_whitelist(emit, regime) is expected


# ----------------------------------------------------------------------
# Rule matching (full rule spec)
# ----------------------------------------------------------------------


def test_matches_all_clauses_must_pass() -> None:
    rule = RuleSpec(
        id="t",
        when={"regime": "LOW_IV_RANGE", "iv_rank_gte": 50},
        emit=EmittedAction.SELL_COVERED_CALL_PARTIAL,
        rationale="(test)",
    )
    # Both clauses true
    ctx = _ctx(market_state=_market_state(regime=Regime.LOW_IV_RANGE, iv_rank=0.60))
    assert matches(rule, ctx) is True
    # First fails
    ctx2 = _ctx(market_state=_market_state(regime=Regime.BREAKOUT, iv_rank=0.60))
    assert matches(rule, ctx2) is False
    # Second fails
    ctx3 = _ctx(market_state=_market_state(regime=Regime.LOW_IV_RANGE, iv_rank=0.30))
    assert matches(rule, ctx3) is False


# ----------------------------------------------------------------------
# Each of the 8 V1 rules fires under the documented conditions
# ----------------------------------------------------------------------


def test_rule_high_iv_sell_call(packaged_rules: tuple[RuleSpec, ...]) -> None:
    """Regime LOW_IV_RANGE + iv_rank=65 + no short call → high_iv_sell_call."""
    ms = _market_state(regime=Regime.LOW_IV_RANGE, iv_rank=0.65)
    rec = recommend(
        market_state=ms,
        flow_score=_flow_score(confidence=0.80),
        positions=_positions(),
        profile=_user_profile(),
        rules=packaged_rules,
    )
    assert rec.matched_rule is not None
    assert rec.matched_rule.rule_id == "high_iv_sell_call"
    assert rec.matched_rule.emit is EmittedAction.SELL_COVERED_CALL_PARTIAL


def test_rule_roll_up_and_out(packaged_rules: tuple[RuleSpec, ...]) -> None:
    """Short call within 1% + DTE ≤ 14 → roll_up_and_out."""
    # BREAKOUT allows ROLL_UP_AND_OUT in the regime whitelist
    rec = recommend(
        market_state=_market_state(regime=Regime.BREAKOUT, iv_rank=0.55),
        flow_score=_flow_score(confidence=0.80),
        positions=_positions(
            has_short_call=True,
            nearest_short_call_strike=100.5,  # within 1%
            nearest_short_call_dte=10,  # ≤ 14
        ),
        profile=_user_profile(),
        rules=packaged_rules,
    )
    assert rec.matched_rule is not None
    assert rec.matched_rule.rule_id == "roll_up_and_out_when_short_call_threatened"
    assert rec.matched_rule.emit is EmittedAction.ROLL_UP_AND_OUT


def test_rule_reduce_coverage_breakout(packaged_rules: tuple[RuleSpec, ...]) -> None:
    """BREAKOUT + days_since_event ≤ 2 + IV crush ≤ -15 → reduce_coverage."""
    rec = recommend(
        market_state=_market_state(
            regime=Regime.BREAKOUT,
            days_since_event=1,
            iv_rank_change_1d=-0.20,
        ),
        flow_score=_flow_score(confidence=0.80),
        positions=_positions(),
        profile=_user_profile(),
        rules=packaged_rules,
    )
    assert rec.matched_rule is not None
    assert rec.matched_rule.rule_id == "reduce_coverage_on_breakout_post_event"


def test_rule_open_collar(packaged_rules: tuple[RuleSpec, ...]) -> None:
    """HIGH_IV_EVENT + event ≤ 7 days + no long put → open_collar_pre_event."""
    rec = recommend(
        market_state=_market_state(
            regime=Regime.HIGH_IV_EVENT,
            days_to_next_event=5,
            next_event_kind="earnings",
            iv_rank=0.40,  # below high_iv_sell_call threshold of 50
        ),
        flow_score=_flow_score(confidence=0.80),
        positions=_positions(),
        profile=_user_profile(),
        rules=packaged_rules,
    )
    assert rec.matched_rule is not None
    assert rec.matched_rule.rule_id == "open_collar_pre_event"


def test_rule_buy_long_dated_put(packaged_rules: tuple[RuleSpec, ...]) -> None:
    """LOW_IV_TREND + low iv_rank + no long put + low drawdown_tolerance."""
    rec = recommend(
        market_state=_market_state(regime=Regime.LOW_IV_TREND, iv_rank=0.25),
        flow_score=_flow_score(confidence=0.80),
        positions=_positions(),
        profile=_user_profile(drawdown_tolerance=0.15),
        rules=packaged_rules,
    )
    assert rec.matched_rule is not None
    assert rec.matched_rule.rule_id == "buy_long_dated_put_low_iv_trend"


def test_rule_monetize_put(packaged_rules: tuple[RuleSpec, ...]) -> None:
    """BREAKOUT + has_long_put + put up 30% → monetize_put."""
    rec = recommend(
        market_state=_market_state(regime=Regime.BREAKOUT),
        flow_score=_flow_score(confidence=0.80),
        positions=_positions(has_long_put=True, long_put_pnl_pct=0.35),
        profile=_user_profile(),
        rules=packaged_rules,
    )
    assert rec.matched_rule is not None
    assert rec.matched_rule.rule_id == "monetize_put_on_breakout"


def test_rule_wheel_short_put(packaged_rules: tuple[RuleSpec, ...]) -> None:
    """LOW_IV_RANGE + no short put + style=income → wheel_short_put."""
    rec = recommend(
        market_state=_market_state(regime=Regime.LOW_IV_RANGE, iv_rank=0.40),
        flow_score=_flow_score(confidence=0.80),
        positions=_positions(),
        profile=_user_profile(style=ProfileStyle.INCOME),
        rules=packaged_rules,
    )
    assert rec.matched_rule is not None
    # Note `high_iv_sell_call` requires iv_rank >= 50; we set 0.40 so it skips.
    assert rec.matched_rule.rule_id == "wheel_on_low_iv_range"


def test_rule_hold_no_op(packaged_rules: tuple[RuleSpec, ...]) -> None:
    """confidence ≤ 0.30 → hold_no_op."""
    rec = recommend(
        market_state=_market_state(
            regime=Regime.LOW_IV_RANGE, regime_score=0.20, iv_rank=0.30
        ),
        flow_score=_flow_score(confidence=0.20),  # low: 0.20 * 0.20 = 0.04
        positions=_positions(),
        profile=_user_profile(),
        rules=packaged_rules,
    )
    assert rec.matched_rule is not None
    assert rec.matched_rule.rule_id == "hold_no_op"
    assert rec.matched_rule.emit is EmittedAction.NO_OP


# ----------------------------------------------------------------------
# Rationale rendering
# ----------------------------------------------------------------------


def test_rationale_substitutes_iv_rank(packaged_rules: tuple[RuleSpec, ...]) -> None:
    ms = _market_state(regime=Regime.LOW_IV_RANGE, iv_rank=0.72)
    rec = recommend(
        market_state=ms,
        flow_score=_flow_score(confidence=0.80),
        positions=_positions(),
        profile=_user_profile(min_iv_rank=40),
        rules=packaged_rules,
    )
    assert rec.matched_rule is not None
    # Template was `IV rank {{iv_rank}} >= sell threshold {{profile.iv_rank_sell_threshold}}`
    assert "IV rank 72" in rec.rationale[0]
    assert "sell threshold 40" in rec.rationale[0]


def test_rationale_substitutes_confidence(packaged_rules: tuple[RuleSpec, ...]) -> None:
    """hold_no_op rationale has {{confidence}} placeholder.

    To force `hold_no_op`, drop iv_rank below the high_iv_sell_call
    threshold (50) AND keep composite confidence below 0.30 so the
    `confidence_lte: 0.30` clause matches. With the M1.10 composer
    (§22.13 multiplicative formula), confidence values shift relative
    to the old `flow × regime` stub — we assert that the rendered
    integer percent appears in the rationale rather than pinning a
    specific value.
    """
    rec = recommend(
        market_state=_market_state(
            regime=Regime.LOW_IV_RANGE, regime_score=0.20, iv_rank=0.30
        ),
        flow_score=_flow_score(confidence=0.20),
        positions=_positions(),
        profile=_user_profile(),
        rules=packaged_rules,
    )
    assert rec.matched_rule is not None
    assert rec.matched_rule.rule_id == "hold_no_op"
    # Rendered as integer percent (see render_rationale): e.g.
    # "Signal alignment too low (17%); no high-conviction action".
    assert f"{int(round(rec.confidence * 100))}%" in rec.rationale[0]


# ----------------------------------------------------------------------
# Confidence + coverage
# ----------------------------------------------------------------------


def test_confidence_is_composer_output(
    packaged_rules: tuple[RuleSpec, ...],
) -> None:
    """M1.10: confidence now flows through `engine.confidence.compose()`.

    The old `flow.confidence × regime_score` stub is replaced by the
    multiplicative formula (§22.13). We re-derive the expected number
    from the composer's component functions so the assertion stays
    valid if calibration constants in `engine.confidence.components`
    are tweaked — only the formula structure is pinned.
    """
    from engine.confidence import (
        DEFAULT_WEIGHTS,
        compose,
        compute_confidence_inputs,
    )

    flow = _flow_score(confidence=0.40)
    ms = _market_state(regime_score=0.60)
    profile = _user_profile()

    rec = recommend(
        market_state=ms,
        flow_score=flow,
        positions=_positions(),
        profile=profile,
        rules=packaged_rules,
    )

    expected_inputs = compute_confidence_inputs(
        market_state=ms, flow_score=flow, profile=profile
    )
    expected_confidence, _ = compose(expected_inputs, DEFAULT_WEIGHTS)
    assert rec.confidence == pytest.approx(expected_confidence, abs=1e-12)
    # The new field is populated by recommend()
    assert rec.confidence_breakdown is not None
    assert rec.confidence_breakdown.weights_version == "v2.0"


def test_coverage_after_sell_covered_call(
    packaged_rules: tuple[RuleSpec, ...],
) -> None:
    """SELL_COVERED_CALL_PARTIAL adds 0.30 contracts per 100 shares."""
    rec = recommend(
        market_state=_market_state(regime=Regime.LOW_IV_RANGE, iv_rank=0.65),
        flow_score=_flow_score(confidence=0.80),
        positions=_positions(underlying_shares=100),
        profile=_user_profile(),
        rules=packaged_rules,
    )
    # 100 shares → 1 covered-call lot → 0.30 contracts → coverage_after = 30/100 = 0.30
    assert rec.matched_rule is not None
    assert rec.matched_rule.emit is EmittedAction.SELL_COVERED_CALL_PARTIAL
    assert rec.coverage_after == pytest.approx(0.30, abs=1e-9)


def test_coverage_after_no_shares() -> None:
    """No underlying shares → coverage_after = 0."""
    packaged = load_rules_yaml(_PACKAGED_RULES_PATH)
    rec = recommend(
        market_state=_market_state(regime=Regime.LOW_IV_RANGE, iv_rank=0.65),
        flow_score=_flow_score(confidence=0.80),
        positions=_positions(underlying_shares=0),
        profile=_user_profile(),
        rules=packaged,
    )
    assert rec.coverage_after == 0.0


# ----------------------------------------------------------------------
# Empty rules validation
# ----------------------------------------------------------------------


def test_recommend_empty_rules_raises() -> None:
    with pytest.raises(ValueError, match="rules.*empty"):
        recommend(
            market_state=_market_state(),
            flow_score=_flow_score(),
            positions=_positions(),
            profile=_user_profile(),
            rules=[],
        )


# ----------------------------------------------------------------------
# Determinism + shape
# ----------------------------------------------------------------------


def test_recommend_returns_shape(packaged_rules: tuple[RuleSpec, ...]) -> None:
    rec = recommend(
        market_state=_market_state(),
        flow_score=_flow_score(),
        positions=_positions(),
        profile=_user_profile(),
        rules=packaged_rules,
    )
    assert isinstance(rec, RecommendationResult)
    assert isinstance(rec.regime, Regime)
    assert 0.0 <= rec.confidence <= 1.0
    assert isinstance(rec.actions, tuple)


def test_recommend_is_deterministic(packaged_rules: tuple[RuleSpec, ...]) -> None:
    a = recommend(
        market_state=_market_state(),
        flow_score=_flow_score(),
        positions=_positions(),
        profile=_user_profile(),
        rules=packaged_rules,
    )
    b = recommend(
        market_state=_market_state(),
        flow_score=_flow_score(),
        positions=_positions(),
        profile=_user_profile(),
        rules=packaged_rules,
    )
    assert a == b


def test_recommendation_result_is_frozen(
    packaged_rules: tuple[RuleSpec, ...],
) -> None:
    from dataclasses import FrozenInstanceError

    rec = recommend(
        market_state=_market_state(),
        flow_score=_flow_score(),
        positions=_positions(),
        profile=_user_profile(),
        rules=packaged_rules,
    )
    with pytest.raises(FrozenInstanceError):
        rec.confidence = 0.5  # type: ignore[misc]


# ----------------------------------------------------------------------
# select_winning_rule diagnostics
# ----------------------------------------------------------------------


def test_select_winning_rule_records_candidates(
    packaged_rules: tuple[RuleSpec, ...],
) -> None:
    """`candidates_considered` lists rules whose emit passed the whitelist."""
    rec = recommend(
        market_state=_market_state(regime=Regime.LOW_IV_RANGE, iv_rank=0.65),
        flow_score=_flow_score(confidence=0.80),
        positions=_positions(),
        profile=_user_profile(),
        rules=packaged_rules,
    )
    # LOW_IV_RANGE whitelist allows SELL_COVERED_CALL_PARTIAL + WHEEL_SHORT_PUT + NO_OP
    # high_iv_sell_call fires first (SELL_COVERED_CALL_PARTIAL emit).
    assert "high_iv_sell_call" in rec.candidates_considered


# ----------------------------------------------------------------------
# Hypothesis property tests
# ----------------------------------------------------------------------


@given(
    confidence=st.floats(min_value=0.0, max_value=1.0),
    regime_score=st.floats(min_value=0.0, max_value=1.0),
    iv_rank=st.floats(min_value=0.0, max_value=1.0),
)
@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_confidence_bounded(
    confidence: float, regime_score: float, iv_rank: float
) -> None:
    rules = load_rules_yaml(_PACKAGED_RULES_PATH)
    rec = recommend(
        market_state=_market_state(regime_score=regime_score, iv_rank=iv_rank),
        flow_score=_flow_score(confidence=confidence),
        positions=_positions(),
        profile=_user_profile(),
        rules=rules,
    )
    assert 0.0 <= rec.confidence <= 1.0


@given(
    regime=st.sampled_from(Regime),
    iv_rank=st.floats(min_value=0.0, max_value=1.0),
    confidence=st.floats(min_value=0.0, max_value=1.0),
)
@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_emit_is_valid_enum(
    regime: Regime, iv_rank: float, confidence: float
) -> None:
    """Across the input space, every emitted action is a valid enum value."""
    rules = load_rules_yaml(_PACKAGED_RULES_PATH)
    rec = recommend(
        market_state=_market_state(regime=regime, iv_rank=iv_rank),
        flow_score=_flow_score(confidence=confidence),
        positions=_positions(),
        profile=_user_profile(),
        rules=rules,
    )
    for action in rec.actions:
        assert action.emit in set(EmittedAction)
    if rec.matched_rule:
        assert rec.matched_rule.emit in set(EmittedAction)


# ----------------------------------------------------------------------
# select_winning_rule direct API
# ----------------------------------------------------------------------


def test_select_winning_rule_none_when_no_match(
    packaged_rules: tuple[RuleSpec, ...],
) -> None:
    """A LOW_IV_TREND regime with no positions and high confidence has no
    rule to fire (hold_no_op needs low confidence; buy_long_dated_put
    needs low IV; etc.). Result: matched=None.
    """
    ctx = EvaluationContext(
        market_state=_market_state(
            regime=Regime.LOW_IV_TREND, iv_rank=0.70  # too high for buy_long_dated_put
        ),
        flow_score=_flow_score(confidence=0.90),  # too high for hold_no_op
        positions=_positions(),
        profile=_user_profile(),
        confidence=0.80,
    )
    matched, candidates = select_winning_rule(rules=packaged_rules, ctx=ctx)
    assert matched is None
    # NO_OP fallback (hold_no_op) was a candidate; not matched at high confidence.
    assert "hold_no_op" in candidates


def test_matched_rule_carries_score_1(packaged_rules: tuple[RuleSpec, ...]) -> None:
    """V1 binary scoring: every matched rule has score=1.0."""
    rec = recommend(
        market_state=_market_state(regime=Regime.LOW_IV_RANGE, iv_rank=0.65),
        flow_score=_flow_score(confidence=0.80),
        positions=_positions(),
        profile=_user_profile(),
        rules=packaged_rules,
    )
    assert rec.matched_rule is not None
    assert rec.matched_rule.score == 1.0
