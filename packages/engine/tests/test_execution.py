"""Execution Feasibility Module (M1.11) tests.

Per plan v1.2 §17 M1.11 acceptance and §9.8 (the formula source).

Test discipline:
  - Per-component formulas verified against §9.8 / docstring math
  - Edge cases: missing quote, inverted bid/ask, oi=0, volume=0,
    qty=0, empty legs
  - Composer integration: liquidity_penalty(execution) plugs into
    recommend(illiquidity_penalty=...) and shrinks confidence
  - Downgrade-threshold semantics (0.50 trigger)
  - Hypothesis property tests: bounded output for any valid inputs
"""

from __future__ import annotations

from datetime import date

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from engine.confidence import compose, compute_confidence_inputs
from engine.execution import (
    DOWNGRADE_THRESHOLD,
    Execution,
    ExecutionLeg,
    OrderType,
    aggregate,
    assess,
    compute_spread_bps,
    expected_slippage,
    fill_confidence,
    limit_price_band,
    liquidity_penalty,
    liquidity_score,
    norm_oi,
    norm_volume,
    size_warnings,
    suggested_order_type,
    tick_size,
)
from engine.flow_score.types import Bias, FlowScore, RecommendedAction
from engine.market_state.classify import MarketStateResult
from engine.profiles import IncomeNeed, ProfileStyle, RiskTolerance, UserStrategyProfile
from engine.recommendation import PositionState, recommend
from engine.recommendation.yaml_loader import load_default_rules
from engine.regimes import Regime
from engine.strike_selector.types import LegSide, StrikeLeg
from engine.types import OptionContract, OptionType

# ----------------------------------------------------------------------
# Fixture helpers
# ----------------------------------------------------------------------


def _contract(
    *,
    bid: float | None = 4.20,
    ask: float | None = 4.30,
    mid: float | None = 4.25,
    open_interest: int = 2500,
    volume: int = 180,
    strike: float = 415.0,
    option_type: OptionType = OptionType.CALL,
) -> OptionContract:
    return OptionContract(
        underlying="MSFT",
        expiry=date(2026, 6, 19),
        strike=strike,
        option_type=option_type,
        bid=bid,
        ask=ask,
        mid=mid,
        iv=0.28,
        open_interest=open_interest,
        volume=volume,
    )


def _leg(
    *,
    contract: OptionContract | None = None,
    side: LegSide = LegSide.SHORT,
) -> StrikeLeg:
    c = contract if contract is not None else _contract()
    return StrikeLeg(
        contract=c,
        side=side,
        delta_target=0.35,
        delta_actual=0.34,
        delta_distance=0.01,
        dte_actual=30,
        mid_price=c.mid,
    )


# ----------------------------------------------------------------------
# norm_oi / norm_volume / compute_spread_bps
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "oi,expected",
    [
        (-1, 0.0),
        (0, 0.0),
        (500, 0.5),
        (1000, 1.0),
        (10_000, 1.0),  # saturates
    ],
)
def test_norm_oi(oi: int, expected: float) -> None:
    assert norm_oi(oi) == pytest.approx(expected, abs=1e-12)


@pytest.mark.parametrize(
    "volume,expected",
    [
        (-1, 0.0),
        (0, 0.0),
        (100, 0.5),
        (200, 1.0),
        (10_000, 1.0),  # saturates
    ],
)
def test_norm_volume(volume: int, expected: float) -> None:
    assert norm_volume(volume) == pytest.approx(expected, abs=1e-12)


def test_compute_spread_bps_typical() -> None:
    # spread = 0.10, mid = 4.25 → 0.10/4.25 * 10000 ≈ 235.29 → 235
    assert compute_spread_bps(bid=4.20, ask=4.30, mid=4.25) == 235


def test_compute_spread_bps_tight() -> None:
    # spread = 0.01, mid = 4.25 → 23.5 → 24 (banker's rounding-aware on .5)
    bps = compute_spread_bps(bid=4.245, ask=4.255, mid=4.25)
    assert bps in {23, 24}  # round-half-to-even ambiguity


def test_compute_spread_bps_wide() -> None:
    # spread = 1.00, mid = 4.50 → 2222 bps
    bps = compute_spread_bps(bid=4.0, ask=5.0, mid=4.5)
    assert bps == pytest.approx(2222, abs=1)


def test_compute_spread_bps_missing_bid() -> None:
    assert compute_spread_bps(bid=None, ask=4.30, mid=4.25) == 9999


def test_compute_spread_bps_missing_ask() -> None:
    assert compute_spread_bps(bid=4.20, ask=None, mid=4.25) == 9999


def test_compute_spread_bps_inverted_quote() -> None:
    # ask < bid → broken quote sentinel
    assert compute_spread_bps(bid=4.30, ask=4.20, mid=4.25) == 9999


def test_compute_spread_bps_equal_quote() -> None:
    # ask == bid → broken (zero-width) quote sentinel
    assert compute_spread_bps(bid=4.25, ask=4.25, mid=4.25) == 9999


def test_compute_spread_bps_mid_fallback() -> None:
    # mid=None → uses (bid+ask)/2 = 4.25
    assert compute_spread_bps(bid=4.20, ask=4.30, mid=None) == 235


def test_compute_spread_bps_mid_floor() -> None:
    # extremely cheap option: mid = $0.005 floored to $0.01
    bps = compute_spread_bps(bid=0.0, ask=0.01, mid=0.005)
    assert bps == 9999  # bid=ask=0.0 still passes (ask>bid) but result is huge / clipped


def test_compute_spread_bps_caps_at_sentinel() -> None:
    # extreme blow-out: spread > 9999 bps clamps
    bps = compute_spread_bps(bid=0.01, ask=10.0, mid=0.01)
    assert bps == 9999


# ----------------------------------------------------------------------
# liquidity_score
# ----------------------------------------------------------------------


def test_liquidity_score_full_saturation_and_zero_spread() -> None:
    # OI=10_000, vol=10_000, spread=0 → all three terms 1.0 → 1.0
    assert liquidity_score(oi=10_000, volume=10_000, spread_bps=0) == 1.0


def test_liquidity_score_zero_oi_zero_volume_wide_spread() -> None:
    # All zeros → 0.0
    assert liquidity_score(oi=0, volume=0, spread_bps=300) == 0.0


def test_liquidity_score_hand_calc_typical() -> None:
    # OI=2500 (saturates), volume=180 (90%), spread=235 bps
    # = 0.4*1.0 + 0.4*0.9 + 0.2*(1-235/300)
    # = 0.40 + 0.36 + 0.2*0.2167 ≈ 0.8033
    assert liquidity_score(
        oi=2500, volume=180, spread_bps=235
    ) == pytest.approx(0.40 + 0.36 + 0.2 * (1 - 235 / 300.0), abs=1e-12)


def test_liquidity_score_spread_above_cap_zero_contribution() -> None:
    # spread_bps=400 ≥ 300 cap → spread component is 0
    score_400 = liquidity_score(oi=2500, volume=180, spread_bps=400)
    score_300 = liquidity_score(oi=2500, volume=180, spread_bps=300)
    assert score_400 == score_300


# ----------------------------------------------------------------------
# expected_slippage
# ----------------------------------------------------------------------


def test_expected_slippage_small_order() -> None:
    # spread=0.10, qty=1, OI=2500 → half_spread (0.05) + tiny size impact
    slip = expected_slippage(bid=4.20, ask=4.30, oi=2500, qty=1)
    half = 0.05
    impact = 0.10 * (1 / 2500.0)
    assert slip == pytest.approx(half + impact, abs=1e-12)


def test_expected_slippage_full_oi_order() -> None:
    # qty == OI → size impact = full spread (1.0 multiplier × clip01(qty/OI) = 1.0)
    slip = expected_slippage(bid=4.20, ask=4.30, oi=10, qty=10)
    half = 0.05
    impact = 0.10  # full spread
    assert slip == pytest.approx(half + impact, abs=1e-12)


def test_expected_slippage_qty_exceeds_oi() -> None:
    # qty > OI: size impact clipped at 1.0 (one full spread)
    slip_10 = expected_slippage(bid=4.20, ask=4.30, oi=10, qty=10)
    slip_100 = expected_slippage(bid=4.20, ask=4.30, oi=10, qty=100)
    assert slip_100 == slip_10  # already at clip


def test_expected_slippage_negative_qty_uses_abs() -> None:
    """Sign of qty doesn't matter for slippage cost."""
    pos = expected_slippage(bid=4.20, ask=4.30, oi=2500, qty=5)
    neg = expected_slippage(bid=4.20, ask=4.30, oi=2500, qty=-5)
    assert pos == neg


def test_expected_slippage_zero_oi() -> None:
    # OI=0 floored to 1 → qty/1 saturates → full-spread impact
    slip = expected_slippage(bid=4.20, ask=4.30, oi=0, qty=1)
    assert slip == pytest.approx(0.05 + 0.10, abs=1e-12)


def test_expected_slippage_missing_quote() -> None:
    assert expected_slippage(bid=None, ask=4.30, oi=2500, qty=1) == 0.0
    assert expected_slippage(bid=4.20, ask=None, oi=2500, qty=1) == 0.0


def test_expected_slippage_inverted_quote() -> None:
    assert expected_slippage(bid=4.30, ask=4.20, oi=2500, qty=1) == 0.0


# ----------------------------------------------------------------------
# fill_confidence + suggested_order_type + DOWNGRADE_THRESHOLD
# ----------------------------------------------------------------------


def test_fill_confidence_hand_calc() -> None:
    # liquidity=0.8, spread=200 → 0.6*0.8 + 0.4*(1-200/300) = 0.48 + 0.4*(1/3) = 0.6133
    assert fill_confidence(liquidity=0.8, spread_bps=200) == pytest.approx(
        0.48 + 0.4 / 3.0, abs=1e-12
    )


def test_fill_confidence_perfect() -> None:
    assert fill_confidence(liquidity=1.0, spread_bps=0) == 1.0


def test_fill_confidence_zero() -> None:
    assert fill_confidence(liquidity=0.0, spread_bps=300) == 0.0


def test_fill_confidence_above_cap_clips_spread() -> None:
    # spread=400 (> 300 cap) clips to 0 contribution
    assert fill_confidence(liquidity=0.5, spread_bps=400) == pytest.approx(
        0.6 * 0.5, abs=1e-12
    )


def test_suggested_order_type_threshold() -> None:
    assert suggested_order_type(0.70) is OrderType.LIMIT
    assert suggested_order_type(0.6999) is OrderType.MARKETABLE_LIMIT
    assert suggested_order_type(1.0) is OrderType.LIMIT
    assert suggested_order_type(0.0) is OrderType.MARKETABLE_LIMIT


def test_downgrade_threshold_is_half() -> None:
    """M1.12 trigger threshold pinned. Don't change without ADR amendment."""
    assert DOWNGRADE_THRESHOLD == 0.50


# ----------------------------------------------------------------------
# tick_size + limit_price_band
# ----------------------------------------------------------------------


@pytest.mark.parametrize("mid,expected_tick", [(0.50, 0.01), (2.99, 0.01), (3.0, 0.05), (50.0, 0.05)])
def test_tick_size(mid: float, expected_tick: float) -> None:
    assert tick_size(mid) == expected_tick


def test_limit_price_band_typical() -> None:
    low, high = limit_price_band(bid=4.20, ask=4.30, mid=4.25)
    assert low == pytest.approx(4.20, abs=1e-12)  # 4.25 - 0.05
    assert high == pytest.approx(4.30, abs=1e-12)  # 4.25 + 0.05


def test_limit_price_band_below_three_dollars() -> None:
    low, high = limit_price_band(bid=2.10, ask=2.20, mid=2.15)
    # tick = 0.01
    assert low == pytest.approx(2.14, abs=1e-12)
    assert high == pytest.approx(2.16, abs=1e-12)


def test_limit_price_band_mid_fallback() -> None:
    """mid=None falls back to (bid+ask)/2."""
    low, high = limit_price_band(bid=4.20, ask=4.30, mid=None)
    assert low == pytest.approx(4.20, abs=1e-12)
    assert high == pytest.approx(4.30, abs=1e-12)


def test_limit_price_band_broken_quote() -> None:
    """No bid/ask/mid → safe sentinel (0, 0)."""
    assert limit_price_band(bid=None, ask=None, mid=None) == (0.0, 0.0)


def test_limit_price_band_clamps_low_at_zero() -> None:
    """A near-zero mid yields a non-negative low bound."""
    low, _ = limit_price_band(bid=0.0, ask=0.02, mid=0.01)
    assert low == 0.0


# ----------------------------------------------------------------------
# size_warnings
# ----------------------------------------------------------------------


def test_size_warnings_below_thresholds() -> None:
    assert size_warnings(oi=2500, volume=180, qty=5) == ()


def test_size_warnings_exceeds_oi_only() -> None:
    # qty=500, OI=2500 → 20% > 10% threshold
    warnings = size_warnings(oi=2500, volume=10_000, qty=500)
    assert len(warnings) == 1
    assert "open interest" in warnings[0]


def test_size_warnings_exceeds_volume_only() -> None:
    # qty=200, OI=10_000, volume=300 → 67% > 50% threshold; qty/OI=2%
    warnings = size_warnings(oi=10_000, volume=300, qty=200)
    assert len(warnings) == 1
    assert "volume" in warnings[0]


def test_size_warnings_both_triggers() -> None:
    warnings = size_warnings(oi=100, volume=10, qty=50)
    assert len(warnings) == 2
    assert any("open interest" in w for w in warnings)
    assert any("volume" in w for w in warnings)


def test_size_warnings_zero_qty() -> None:
    assert size_warnings(oi=2500, volume=180, qty=0) == ()


def test_size_warnings_negative_qty_uses_abs() -> None:
    assert size_warnings(oi=100, volume=10, qty=-50) == size_warnings(
        oi=100, volume=10, qty=50
    )


# ----------------------------------------------------------------------
# assess() — orchestrator + per-leg pipeline
# ----------------------------------------------------------------------


def test_assess_single_healthy_leg() -> None:
    """End-to-end hand calc on a clean, liquid call leg."""
    exe = assess(legs=[_leg()])
    assert len(exe.legs) == 1
    leg0 = exe.legs[0]
    # spread = 0.10, mid = 4.25 → 235 bps
    assert leg0.spread_bps == 235
    # liquidity = 0.4*1.0 + 0.4*0.9 + 0.2*(1-235/300) ≈ 0.8033
    assert leg0.liquidity_score == pytest.approx(
        0.4 + 0.36 + 0.2 * (1 - 235 / 300.0), abs=1e-12
    )
    # fill = 0.6*liq + 0.4*(1-235/300) ≈ 0.5687
    expected_fill = 0.6 * leg0.liquidity_score + 0.4 * (1 - 235 / 300.0)
    assert leg0.fill_confidence == pytest.approx(expected_fill, abs=1e-12)
    # 0.5687 < 0.70 → MARKETABLE_LIMIT
    assert leg0.suggested_order_type is OrderType.MARKETABLE_LIMIT


def test_assess_empty_legs_returns_trivial_execution() -> None:
    """REDUCE_COVERAGE / MONETIZE_PUT / NO_OP all hit this path."""
    exe = assess(legs=[])
    assert exe.aggregate_liquidity_score == 1.0
    assert exe.aggregate_fill_confidence == 1.0
    assert exe.suggested_order_type is OrderType.LIMIT
    assert exe.legs == ()
    assert exe.notes == ()
    # And the composer bridge: no legs → no illiquidity penalty.
    assert liquidity_penalty(exe) == 0.0


def test_assess_two_legs_collar() -> None:
    """OPEN_COLLAR-style: SHORT call + LONG put."""
    call = _contract(strike=420.0, option_type=OptionType.CALL, bid=3.5, ask=3.6, mid=3.55)
    put = _contract(strike=400.0, option_type=OptionType.PUT, bid=4.0, ask=4.1, mid=4.05)
    legs = [
        _leg(contract=call, side=LegSide.SHORT),
        _leg(contract=put, side=LegSide.LONG),
    ]
    exe = assess(legs=legs)
    assert len(exe.legs) == 2
    # Aggregate = min of legs
    assert exe.aggregate_liquidity_score == min(
        exe.legs[0].liquidity_score, exe.legs[1].liquidity_score
    )
    assert exe.aggregate_fill_confidence == min(
        exe.legs[0].fill_confidence, exe.legs[1].fill_confidence
    )


def test_assess_broken_quote_drops_liquidity_to_zero() -> None:
    """Missing bid/ask → spread_bps sentinel → liquidity term contributes only OI/volume."""
    c = _contract(bid=None, ask=None, mid=None, open_interest=2500, volume=180)
    exe = assess(legs=[_leg(contract=c)])
    leg0 = exe.legs[0]
    # spread_bps = 9999 sentinel → spread component = clip01(1 - 9999/300) = 0
    # liquidity = 0.4*1.0 + 0.4*0.9 + 0.2*0.0 = 0.76
    assert leg0.liquidity_score == pytest.approx(0.4 + 0.36, abs=1e-12)
    # fill = 0.6*0.76 + 0.4*0.0 = 0.456 → MARKETABLE_LIMIT
    assert leg0.fill_confidence == pytest.approx(0.6 * 0.76, abs=1e-12)
    assert leg0.suggested_order_type is OrderType.MARKETABLE_LIMIT


def test_assess_quantities_length_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="doesn't match"):
        assess(legs=[_leg()], quantities=[1, 2])


def test_assess_quantities_default_is_one_per_leg() -> None:
    """No quantities arg → 1 per leg. Verify by comparing to explicit [1]."""
    exe_default = assess(legs=[_leg()])
    exe_explicit = assess(legs=[_leg()], quantities=[1])
    assert exe_default == exe_explicit


def test_assess_large_qty_triggers_size_warning_in_notes() -> None:
    c = _contract(open_interest=100, volume=10)  # tiny strike
    exe = assess(legs=[_leg(contract=c)], quantities=[50])
    # 50 > 10% of 100 AND 50 > 50% of 10 → both warnings
    assert len(exe.legs[0].size_warnings) == 2
    # And they should bubble up into top-level notes
    assert len(exe.notes) >= 2


def test_assess_downgrade_hint_added_when_aggregate_below_threshold() -> None:
    """Aggregate fill below 0.50 → notes includes M1.12 downgrade hint."""
    # Wide spread + thin OI → fill should be well below 0.50
    c = _contract(bid=4.0, ask=5.0, mid=4.5, open_interest=10, volume=2)
    exe = assess(legs=[_leg(contract=c)])
    assert exe.aggregate_fill_confidence < DOWNGRADE_THRESHOLD
    assert any("downgrade callback" in note for note in exe.notes)


def test_assess_pure_function_determinism() -> None:
    """Same inputs → byte-identical Execution (per ADR-0005)."""
    a = assess(legs=[_leg()])
    b = assess(legs=[_leg()])
    assert a == b


def test_assess_leg_id_format() -> None:
    leg = _leg()
    exe = assess(legs=[leg])
    # short_call_415.0_2026-06-19
    assert exe.legs[0].leg_id == "short_call_415.0_2026-06-19"


# ----------------------------------------------------------------------
# aggregate()
# ----------------------------------------------------------------------


def test_aggregate_empty_legs() -> None:
    agg_liq, agg_fill, order_type, notes = aggregate([])
    assert agg_liq == 1.0
    assert agg_fill == 1.0
    assert order_type is OrderType.LIMIT
    assert notes == ()


def test_aggregate_weakest_link() -> None:
    """Aggregate scores = min across legs."""
    leg_a = ExecutionLeg(
        leg_id="a", liquidity_score=0.80, spread_bps=100,
        fill_confidence=0.75, expected_slippage=0.05,
        suggested_order_type=OrderType.LIMIT, limit_price_band=(4.20, 4.30),
        size_warnings=(),
    )
    leg_b = ExecutionLeg(
        leg_id="b", liquidity_score=0.30, spread_bps=400,
        fill_confidence=0.35, expected_slippage=0.30,
        suggested_order_type=OrderType.MARKETABLE_LIMIT, limit_price_band=(3.95, 4.05),
        size_warnings=(),
    )
    agg_liq, agg_fill, order_type, notes = aggregate([leg_a, leg_b])
    assert agg_liq == 0.30
    assert agg_fill == 0.35
    # leg_b fill < 0.70 → aggregate is MARKETABLE_LIMIT
    assert order_type is OrderType.MARKETABLE_LIMIT
    # leg_b fill < 0.50 → downgrade hint
    assert any("downgrade callback" in n for n in notes)


def test_aggregate_all_legs_above_limit_threshold() -> None:
    """When every leg ≥ 0.70 fill → aggregate order type is LIMIT."""
    legs = tuple(
        ExecutionLeg(
            leg_id=f"l{i}", liquidity_score=0.95, spread_bps=50,
            fill_confidence=0.85, expected_slippage=0.02,
            suggested_order_type=OrderType.LIMIT, limit_price_band=(4.20, 4.30),
            size_warnings=(),
        )
        for i in range(3)
    )
    agg_liq, agg_fill, order_type, _ = aggregate(legs)
    assert agg_liq == 0.95
    assert agg_fill == 0.85
    assert order_type is OrderType.LIMIT


# ----------------------------------------------------------------------
# liquidity_penalty (composer bridge)
# ----------------------------------------------------------------------


def test_liquidity_penalty_perfect_execution_is_zero() -> None:
    """High fill confidence → low illiquidity_penalty."""
    exe = Execution(
        aggregate_liquidity_score=1.0,
        aggregate_fill_confidence=1.0,
        suggested_order_type=OrderType.LIMIT,
        legs=(),
        notes=(),
    )
    assert liquidity_penalty(exe) == 0.0


def test_liquidity_penalty_zero_fill_is_one() -> None:
    """Aggregate fill 0 → illiquidity_penalty 1.0 (worst case)."""
    exe = Execution(
        aggregate_liquidity_score=0.0,
        aggregate_fill_confidence=0.0,
        suggested_order_type=OrderType.MARKETABLE_LIMIT,
        legs=(),
        notes=(),
    )
    assert liquidity_penalty(exe) == 1.0


def test_liquidity_penalty_inverse_of_fill_confidence() -> None:
    """illiquidity_penalty = 1.0 - aggregate_fill_confidence (clipped)."""
    for fill in [0.0, 0.25, 0.50, 0.75, 1.0]:
        exe = Execution(
            aggregate_liquidity_score=fill,
            aggregate_fill_confidence=fill,
            suggested_order_type=OrderType.LIMIT,
            legs=(),
            notes=(),
        )
        assert liquidity_penalty(exe) == pytest.approx(1.0 - fill, abs=1e-12)


# ----------------------------------------------------------------------
# Confidence Composer integration (M1.10 + M1.11)
# ----------------------------------------------------------------------


def _profile() -> UserStrategyProfile:
    return UserStrategyProfile(
        risk_tolerance=RiskTolerance.MODERATE,
        income_need=IncomeNeed.MEDIUM,
        max_position_pct=0.50,
        max_coverage_pct=0.75,
        min_iv_rank_for_short_premium=40,
        prefer_collars_over_covered_calls=False,
        drawdown_tolerance=0.15,
        style=ProfileStyle.BALANCED,
    )


def _market_state() -> MarketStateResult:
    return MarketStateResult(
        regime=Regime.LOW_IV_RANGE,
        regime_score=0.60,
        all_scores={r: 0.0 for r in Regime},
        tags=(),
        spot=415.0,
        iv_rank=0.50,
        iv_percentile=0.50,
        hv_30=0.20,
        expected_move_pct=0.04,
        max_pain=415.0,
        max_pain_delta_pct=0.0,
        pcr_volume=0.50,
        pcr_oi=0.50,
        trend_strength=0.30,
        realized_vs_implied=1.0,
        breakout_signal=0.0,
        oi_concentration_at_max_pain=0.20,
        days_to_next_event=None,
        next_event_kind=None,
        days_since_event=None,
        days_to_nearest_opex=None,
        iv_rank_change_1d=0.0,
        gap_pct=None,
    )


def _flow_score(confidence: float = 0.60, score: float = 20.0) -> FlowScore:
    return FlowScore(
        score=score, bullish_score=max(score, 0.0), bearish_score=max(-score, 0.0),
        bias=Bias.NEUTRAL, recommended_action=RecommendedAction.MONITOR,
        pin_probability=0.0, gamma_risk=0.20, gamma_sign=0,
        confidence=confidence, explanation="(test)", breakdown={},
    )


def test_liquidity_penalty_lowers_confidence_via_recommend() -> None:
    """End-to-end: illiquid Execution → recommend()'s confidence drops by the cap."""
    rules = load_default_rules()
    healthy_exe = Execution(
        aggregate_liquidity_score=1.0, aggregate_fill_confidence=1.0,
        suggested_order_type=OrderType.LIMIT, legs=(), notes=(),
    )
    poor_exe = Execution(
        aggregate_liquidity_score=0.2, aggregate_fill_confidence=0.2,
        suggested_order_type=OrderType.MARKETABLE_LIMIT, legs=(), notes=(),
    )

    common = dict(
        market_state=_market_state(),
        flow_score=_flow_score(),
        positions=PositionState(),
        profile=_profile(),
        rules=rules,
    )
    healthy_rec = recommend(**common, illiquidity_penalty=liquidity_penalty(healthy_exe))
    poor_rec = recommend(**common, illiquidity_penalty=liquidity_penalty(poor_exe))

    # Healthy execution → no extra penalty
    assert liquidity_penalty(healthy_exe) == 0.0
    # Poor execution → penalty of 0.8 → confidence drops by 0.25 * 0.8 = 20%
    assert liquidity_penalty(poor_exe) == pytest.approx(0.8, abs=1e-12)
    assert poor_rec.confidence == pytest.approx(
        healthy_rec.confidence * (1.0 - 0.25 * 0.8), abs=1e-12
    )


def test_liquidity_penalty_via_compute_confidence_inputs() -> None:
    """Direct M1.13-style integration: assess() → liquidity_penalty() → compose()."""
    leg = _leg()  # healthy leg
    exe = assess(legs=[leg])
    penalty = liquidity_penalty(exe)
    inputs = compute_confidence_inputs(
        market_state=_market_state(),
        flow_score=_flow_score(),
        profile=_profile(),
        illiquidity_penalty=penalty,
    )
    assert inputs.illiquidity_penalty == pytest.approx(penalty, abs=1e-12)
    # Run the composer and confirm the breakdown reflects the penalty
    from engine.confidence import DEFAULT_WEIGHTS

    _, breakdown = compose(inputs, DEFAULT_WEIGHTS)
    assert breakdown.illiquidity_penalty == pytest.approx(penalty, abs=1e-12)


# ----------------------------------------------------------------------
# Hypothesis property tests
# ----------------------------------------------------------------------


_oi = st.integers(min_value=0, max_value=50_000)
_vol = st.integers(min_value=0, max_value=50_000)
_spread_bps = st.integers(min_value=0, max_value=9999)


@settings(suppress_health_check=[HealthCheck.too_slow], deadline=None, max_examples=200)
@given(oi=_oi, volume=_vol, spread_bps=_spread_bps)
def test_liquidity_score_is_bounded(oi: int, volume: int, spread_bps: int) -> None:
    s = liquidity_score(oi=oi, volume=volume, spread_bps=spread_bps)
    assert 0.0 <= s <= 1.0


@settings(suppress_health_check=[HealthCheck.too_slow], deadline=None, max_examples=200)
@given(
    liquidity=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    spread_bps=_spread_bps,
)
def test_fill_confidence_is_bounded(liquidity: float, spread_bps: int) -> None:
    f = fill_confidence(liquidity=liquidity, spread_bps=spread_bps)
    assert 0.0 <= f <= 1.0


@settings(suppress_health_check=[HealthCheck.too_slow], deadline=None, max_examples=100)
@given(
    bid=st.floats(min_value=0.01, max_value=100.0, allow_nan=False, allow_infinity=False),
    spread=st.floats(min_value=0.01, max_value=10.0, allow_nan=False, allow_infinity=False),
    oi=_oi,
    qty=st.integers(min_value=0, max_value=10_000),
)
def test_expected_slippage_is_non_negative(
    bid: float, spread: float, oi: int, qty: int
) -> None:
    ask = bid + spread
    slip = expected_slippage(bid=bid, ask=ask, oi=oi, qty=qty)
    assert slip >= 0.0


@settings(suppress_health_check=[HealthCheck.too_slow], deadline=None, max_examples=50)
@given(
    fill=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)
def test_liquidity_penalty_is_bounded(fill: float) -> None:
    """liquidity_penalty(exe) in [0, 1] for any aggregate_fill_confidence in [0, 1]."""
    exe = Execution(
        aggregate_liquidity_score=fill,
        aggregate_fill_confidence=fill,
        suggested_order_type=OrderType.LIMIT,
        legs=(),
        notes=(),
    )
    p = liquidity_penalty(exe)
    assert 0.0 <= p <= 1.0
    assert p == pytest.approx(1.0 - fill, abs=1e-12)
