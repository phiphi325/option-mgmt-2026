"""Confidence Composer (M1.10) tests.

Per plan v1.2 §17 M1.10 acceptance, §9.7, §22.13, and ADR-0003.

Test discipline:
  - Validation invariants on types (range, sum-to-1, etc.)
  - §22.13 worked example pinned exactly (acts as a calibration anchor)
  - Per-component formulas verified against their docstring math
  - YAML loader: malformed inputs (missing keys, wrong types, sums)
  - Drift check: `DEFAULT_WEIGHTS == load_default_weights()`
  - `recommend()` integration: weights kwarg + breakdown wiring
  - Hypothesis property tests for bounded output + determinism
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from engine.confidence import (
    DEFAULT_WEIGHTS,
    ConfidenceInputs,
    PenaltyCaps,
    PositiveWeights,
    Weights,
    compose,
    compute_confidence_inputs,
    compute_event_risk_penalty,
    compute_flow_alignment,
    compute_illiquidity_penalty,
    compute_regime_match,
    compute_signal_alignment,
    compute_structure_alignment,
    load_default_weights,
    load_weights_yaml,
)
from engine.confidence.yaml_loader import _parse_weights_text
from engine.flow_score.types import Bias, FlowScore, RecommendedAction
from engine.market_state.classify import MarketStateResult
from engine.profiles import IncomeNeed, ProfileStyle, RiskTolerance, UserStrategyProfile
from engine.recommendation import PositionState, recommend
from engine.recommendation.yaml_loader import load_default_rules
from engine.regimes import Regime

# ----------------------------------------------------------------------
# Fixtures + helpers
# ----------------------------------------------------------------------


_PACKAGED_WEIGHTS_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "weights.yaml"
)


def _good_inputs(**overrides: float) -> ConfidenceInputs:
    """Build a valid ConfidenceInputs with overrides for one-off tests."""
    defaults = dict(
        flow_alignment=0.50,
        structure_alignment=0.50,
        regime_match=0.50,
        signal_alignment=0.50,
        event_risk_penalty=0.0,
        illiquidity_penalty=0.0,
    )
    defaults.update(overrides)
    return ConfidenceInputs(**defaults)


def _flow_score(
    *,
    confidence: float = 0.5,
    score: float = 0.0,
    bias: Bias = Bias.NEUTRAL,
) -> FlowScore:
    return FlowScore(
        score=score,
        bullish_score=max(score, 0.0),
        bearish_score=max(-score, 0.0),
        bias=bias,
        recommended_action=RecommendedAction.MONITOR,
        pin_probability=0.0,
        gamma_risk=0.20,
        gamma_sign=0,
        confidence=confidence,
        explanation="(test)",
        breakdown={},
    )


def _market_state(
    *,
    regime: Regime = Regime.LOW_IV_RANGE,
    regime_score: float = 0.50,
    trend_strength: float = 0.30,
    breakout_signal: float = 0.0,
    oi_concentration_at_max_pain: float = 0.20,
    days_to_next_event: int | None = None,
) -> MarketStateResult:
    return MarketStateResult(
        regime=regime,
        regime_score=regime_score,
        all_scores={r: 0.0 for r in Regime},
        tags=(),
        spot=100.0,
        iv_rank=0.50,
        iv_percentile=0.50,
        hv_30=0.20,
        expected_move_pct=0.04,
        max_pain=100.0,
        max_pain_delta_pct=0.0,
        pcr_volume=0.50,
        pcr_oi=0.50,
        trend_strength=trend_strength,
        realized_vs_implied=1.0,
        breakout_signal=breakout_signal,
        oi_concentration_at_max_pain=oi_concentration_at_max_pain,
        days_to_next_event=days_to_next_event,
        next_event_kind=None,
        days_since_event=None,
        days_to_nearest_opex=None,
        iv_rank_change_1d=0.0,
        gap_pct=None,
    )


def _profile(*, drawdown_tolerance: float = 0.15) -> UserStrategyProfile:
    return UserStrategyProfile(
        risk_tolerance=RiskTolerance.MODERATE,
        income_need=IncomeNeed.MEDIUM,
        max_position_pct=0.50,
        max_coverage_pct=0.75,
        min_iv_rank_for_short_premium=40,
        prefer_collars_over_covered_calls=False,
        drawdown_tolerance=drawdown_tolerance,
        style=ProfileStyle.BALANCED,
    )


# ----------------------------------------------------------------------
# Type-level validation
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "field",
    [
        "flow_alignment",
        "structure_alignment",
        "regime_match",
        "signal_alignment",
        "event_risk_penalty",
        "illiquidity_penalty",
    ],
)
def test_confidence_inputs_rejects_below_zero(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        _good_inputs(**{field: -0.01})


@pytest.mark.parametrize(
    "field",
    [
        "flow_alignment",
        "structure_alignment",
        "regime_match",
        "signal_alignment",
        "event_risk_penalty",
        "illiquidity_penalty",
    ],
)
def test_confidence_inputs_rejects_above_one(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        _good_inputs(**{field: 1.01})


def test_confidence_inputs_accepts_boundary_values() -> None:
    """0.0 and 1.0 are inclusive — the composer needs these for clip01 anchors."""
    ConfidenceInputs(
        flow_alignment=0.0,
        structure_alignment=1.0,
        regime_match=0.0,
        signal_alignment=1.0,
        event_risk_penalty=0.0,
        illiquidity_penalty=1.0,
    )


def test_weights_rejects_non_unit_positive_sum() -> None:
    with pytest.raises(ValueError, match="must sum to 1.0"):
        Weights(
            version="bad",
            positive_weights=PositiveWeights(
                flow=0.30, struct=0.30, regime=0.30, signal=0.30  # sums to 1.20
            ),
            penalty_caps=PenaltyCaps(event=0.10, liquidity=0.10),
        )


def test_weights_accepts_sum_within_tolerance() -> None:
    """1e-7 of fuzz is admitted; 1e-5 is rejected."""
    # Within tolerance: 0.30 + 0.25 + 0.25 + 0.20 + 1e-7 ≈ 1.0
    Weights(
        version="ok",
        positive_weights=PositiveWeights(
            flow=0.30 + 1e-7, struct=0.25, regime=0.25, signal=0.20
        ),
        penalty_caps=PenaltyCaps(event=0.30, liquidity=0.25),
    )
    # Outside tolerance: total = 1.00001 → fails
    with pytest.raises(ValueError, match="must sum to 1.0"):
        Weights(
            version="too-loose",
            positive_weights=PositiveWeights(
                flow=0.30001, struct=0.25, regime=0.25, signal=0.20
            ),
            penalty_caps=PenaltyCaps(event=0.30, liquidity=0.25),
        )


def test_weights_rejects_negative_positive_weight() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        Weights(
            version="negative",
            positive_weights=PositiveWeights(
                flow=-0.10, struct=0.30, regime=0.30, signal=0.50  # sums to 1.00
            ),
            penalty_caps=PenaltyCaps(event=0.10, liquidity=0.10),
        )


@pytest.mark.parametrize("cap", ["event", "liquidity"])
def test_weights_rejects_out_of_range_penalty_cap(cap: str) -> None:
    base = dict(event=0.30, liquidity=0.25)
    base[cap] = 1.5
    with pytest.raises(ValueError, match=cap):
        Weights(
            version="bad-cap",
            positive_weights=PositiveWeights(
                flow=0.30, struct=0.25, regime=0.25, signal=0.20
            ),
            penalty_caps=PenaltyCaps(**base),
        )


# ----------------------------------------------------------------------
# compose() — formula correctness
# ----------------------------------------------------------------------


def test_compose_matches_plan_section_22_13_worked_example() -> None:
    """§22.13 worked example.

    positive       = 0.30·0.80 + 0.25·0.70 + 0.25·0.90 + 0.20·0.75 = 0.79
    penalty_mult   = (1 − 0.30·0.10) · (1 − 0.25·0.05) = 0.97 · 0.9875 = 0.957875
    confidence     = clip01(0.79 · 0.957875) ≈ 0.7567

    The plan rounds `penalty_mult` to 0.9579 and `confidence` to 0.76.
    We compute exactly and round to 4 / 2 decimals respectively.
    """
    inputs = ConfidenceInputs(
        flow_alignment=0.80,
        structure_alignment=0.70,
        regime_match=0.90,
        signal_alignment=0.75,
        event_risk_penalty=0.10,
        illiquidity_penalty=0.05,
    )
    confidence, breakdown = compose(inputs, DEFAULT_WEIGHTS)
    assert breakdown.positive_score == pytest.approx(0.79, abs=1e-12)
    # Exact: 0.97 * 0.9875 = 0.957875 (plan rounds to 0.9579 / 4 dp).
    assert breakdown.penalty_multiplier == pytest.approx(0.957875, abs=1e-12)
    assert round(breakdown.penalty_multiplier, 4) == 0.9579
    assert confidence == pytest.approx(0.79 * 0.957875, abs=1e-12)
    # The plan states "≈ 0.76".
    assert round(confidence, 2) == 0.76
    assert breakdown.weights_version == "v2.0"


def test_compose_perfect_components_yields_unity() -> None:
    """All positive components at 1.0, no penalties → confidence = 1.0."""
    inputs = ConfidenceInputs(
        flow_alignment=1.0,
        structure_alignment=1.0,
        regime_match=1.0,
        signal_alignment=1.0,
        event_risk_penalty=0.0,
        illiquidity_penalty=0.0,
    )
    confidence, breakdown = compose(inputs, DEFAULT_WEIGHTS)
    assert confidence == pytest.approx(1.0, abs=1e-12)
    assert breakdown.positive_score == pytest.approx(1.0, abs=1e-12)
    assert breakdown.penalty_multiplier == pytest.approx(1.0, abs=1e-12)


def test_compose_zero_components_yields_zero() -> None:
    """All zeros → confidence = 0.0 regardless of penalty multiplier."""
    inputs = ConfidenceInputs(
        flow_alignment=0.0,
        structure_alignment=0.0,
        regime_match=0.0,
        signal_alignment=0.0,
        event_risk_penalty=1.0,
        illiquidity_penalty=1.0,
    )
    confidence, breakdown = compose(inputs, DEFAULT_WEIGHTS)
    assert confidence == 0.0
    assert breakdown.positive_score == 0.0


def test_compose_max_penalties_reduce_by_cap_factors() -> None:
    """penalty=1.0 reduces confidence by the cap (multiplicatively)."""
    inputs = ConfidenceInputs(
        flow_alignment=1.0,
        structure_alignment=1.0,
        regime_match=1.0,
        signal_alignment=1.0,
        event_risk_penalty=1.0,
        illiquidity_penalty=1.0,
    )
    confidence, breakdown = compose(inputs, DEFAULT_WEIGHTS)
    # (1 - 0.30) × (1 - 0.25) = 0.70 × 0.75 = 0.525
    assert breakdown.penalty_multiplier == pytest.approx(0.525, abs=1e-12)
    assert confidence == pytest.approx(0.525, abs=1e-12)


def test_compose_event_only_penalty_isolated() -> None:
    """Event penalty alone should apply only the event cap."""
    inputs = _good_inputs(
        flow_alignment=1.0,
        structure_alignment=1.0,
        regime_match=1.0,
        signal_alignment=1.0,
        event_risk_penalty=1.0,
        illiquidity_penalty=0.0,
    )
    confidence, breakdown = compose(inputs, DEFAULT_WEIGHTS)
    assert breakdown.penalty_multiplier == pytest.approx(0.70, abs=1e-12)
    assert confidence == pytest.approx(0.70, abs=1e-12)


def test_compose_liquidity_only_penalty_isolated() -> None:
    inputs = _good_inputs(
        flow_alignment=1.0,
        structure_alignment=1.0,
        regime_match=1.0,
        signal_alignment=1.0,
        event_risk_penalty=0.0,
        illiquidity_penalty=1.0,
    )
    confidence, breakdown = compose(inputs, DEFAULT_WEIGHTS)
    assert breakdown.penalty_multiplier == pytest.approx(0.75, abs=1e-12)
    assert confidence == pytest.approx(0.75, abs=1e-12)


def test_compose_breakdown_carries_inputs_back() -> None:
    """ConfidenceBreakdown re-exports every input field for explainability."""
    inputs = ConfidenceInputs(
        flow_alignment=0.11,
        structure_alignment=0.22,
        regime_match=0.33,
        signal_alignment=0.44,
        event_risk_penalty=0.55,
        illiquidity_penalty=0.66,
    )
    _, breakdown = compose(inputs, DEFAULT_WEIGHTS)
    assert breakdown.flow_alignment == 0.11
    assert breakdown.structure_alignment == 0.22
    assert breakdown.regime_match == 0.33
    assert breakdown.signal_alignment == 0.44
    assert breakdown.event_risk_penalty == 0.55
    assert breakdown.illiquidity_penalty == 0.66


# ----------------------------------------------------------------------
# Component scorers — formula correctness
# ----------------------------------------------------------------------


def test_compute_flow_alignment_blends_confidence_and_magnitude() -> None:
    """0.5 × flow.confidence + 0.5 × |score| / 100."""
    fs = _flow_score(confidence=0.80, score=40.0)
    assert compute_flow_alignment(fs) == pytest.approx(
        0.5 * 0.80 + 0.5 * 0.40, abs=1e-12
    )


def test_compute_flow_alignment_neutral_low() -> None:
    """NEUTRAL with score=0 and low confidence → near zero alignment."""
    fs = _flow_score(confidence=0.10, score=0.0)
    assert compute_flow_alignment(fs) == pytest.approx(0.05, abs=1e-12)


def test_compute_flow_alignment_bearish_uses_magnitude() -> None:
    """A strongly bearish flow (negative score) has high magnitude."""
    fs = _flow_score(confidence=0.20, score=-80.0)
    assert compute_flow_alignment(fs) == pytest.approx(
        0.5 * 0.20 + 0.5 * 0.80, abs=1e-12
    )


def test_compute_structure_alignment_weighted_blend() -> None:
    ms = _market_state(
        trend_strength=0.60, breakout_signal=0.40, oi_concentration_at_max_pain=0.80
    )
    assert compute_structure_alignment(ms) == pytest.approx(
        0.50 * 0.60 + 0.30 * 0.40 + 0.20 * 0.80, abs=1e-12
    )


def test_compute_regime_match_is_passthrough() -> None:
    ms = _market_state(regime_score=0.73)
    assert compute_regime_match(ms) == pytest.approx(0.73, abs=1e-12)


def test_compute_signal_alignment_blends_regime_and_flow_confidence() -> None:
    fs = _flow_score(confidence=0.30)
    ms = _market_state(regime_score=0.90)
    assert compute_signal_alignment(ms, fs) == pytest.approx(
        0.5 * 0.90 + 0.5 * 0.30, abs=1e-12
    )


def test_compute_event_risk_penalty_none_event_yields_zero() -> None:
    ms = _market_state(days_to_next_event=None)
    profile = _profile()
    assert compute_event_risk_penalty(ms, profile) == 0.0


def test_compute_event_risk_penalty_far_event_yields_zero() -> None:
    ms = _market_state(days_to_next_event=60)
    assert compute_event_risk_penalty(ms, _profile()) == 0.0


def test_compute_event_risk_penalty_linear_ramp() -> None:
    """0 days → 1.0; 30 days → 0.0; midpoint follows linear interpolation."""
    for days, expected in [(0, 1.0), (15, 0.5), (30, 0.0)]:
        ms = _market_state(days_to_next_event=days)
        assert compute_event_risk_penalty(ms, _profile()) == pytest.approx(
            expected, abs=1e-12
        ), f"days={days}"


def test_compute_event_risk_penalty_low_tolerance_boost() -> None:
    """drawdown_tolerance < 0.10 boosts penalty by 1.5×."""
    ms = _market_state(days_to_next_event=20)  # raw = (30-20)/30 = 1/3
    low_tolerance = _profile(drawdown_tolerance=0.05)
    normal_tolerance = _profile(drawdown_tolerance=0.15)
    raw = 1.0 - 20.0 / 30.0
    assert compute_event_risk_penalty(ms, normal_tolerance) == pytest.approx(
        raw, abs=1e-12
    )
    assert compute_event_risk_penalty(ms, low_tolerance) == pytest.approx(
        raw * 1.5, abs=1e-12
    )


def test_compute_event_risk_penalty_boost_clips_at_one() -> None:
    """0 days × 1.5 boost = 1.5, but the result must be clipped to 1.0."""
    ms = _market_state(days_to_next_event=0)
    low = _profile(drawdown_tolerance=0.05)
    assert compute_event_risk_penalty(ms, low) == 1.0


def test_compute_illiquidity_penalty_is_zero_in_v1() -> None:
    """M1.11 stub — always 0.0 until Execution Feasibility lands."""
    assert compute_illiquidity_penalty() == 0.0


def test_compute_confidence_inputs_aggregates_all_components() -> None:
    """The aggregate constructor wires every component into ConfidenceInputs."""
    fs = _flow_score(confidence=0.5, score=20.0)
    ms = _market_state(
        regime_score=0.70,
        trend_strength=0.40,
        breakout_signal=0.10,
        oi_concentration_at_max_pain=0.30,
        days_to_next_event=10,
    )
    profile = _profile()
    inputs = compute_confidence_inputs(market_state=ms, flow_score=fs, profile=profile)
    assert inputs.flow_alignment == compute_flow_alignment(fs)
    assert inputs.structure_alignment == compute_structure_alignment(ms)
    assert inputs.regime_match == compute_regime_match(ms)
    assert inputs.signal_alignment == compute_signal_alignment(ms, fs)
    assert inputs.event_risk_penalty == compute_event_risk_penalty(ms, profile)
    assert inputs.illiquidity_penalty == 0.0


def test_compute_confidence_inputs_accepts_explicit_illiquidity() -> None:
    """M1.11 will pass a real value through this kwarg."""
    inputs = compute_confidence_inputs(
        market_state=_market_state(),
        flow_score=_flow_score(),
        profile=_profile(),
        illiquidity_penalty=0.42,
    )
    assert inputs.illiquidity_penalty == 0.42


def test_compute_confidence_inputs_clips_illiquidity_above_one() -> None:
    inputs = compute_confidence_inputs(
        market_state=_market_state(),
        flow_score=_flow_score(),
        profile=_profile(),
        illiquidity_penalty=10.0,
    )
    assert inputs.illiquidity_penalty == 1.0


# ----------------------------------------------------------------------
# YAML loader
# ----------------------------------------------------------------------


def test_load_default_weights_returns_v2_zero() -> None:
    w = load_default_weights()
    assert w.version == "v2.0"
    assert w.positive_weights.flow == 0.30
    assert w.positive_weights.struct == 0.25
    assert w.positive_weights.regime == 0.25
    assert w.positive_weights.signal == 0.20
    assert w.penalty_caps.event == 0.30
    assert w.penalty_caps.liquidity == 0.25


def test_default_weights_matches_yaml_drift_check() -> None:
    """The in-code DEFAULT_WEIGHTS constant must equal the on-disk YAML.

    This is the M1.10 equivalent of the shared-types codegen drift
    check: edit one without the other and CI catches it.
    """
    on_disk = load_default_weights()
    assert on_disk == DEFAULT_WEIGHTS


def test_load_weights_yaml_file_not_found() -> None:
    with pytest.raises(FileNotFoundError, match="weights.yaml not found"):
        load_weights_yaml(Path("/nonexistent/weights.yaml"))


def test_load_weights_yaml_empty() -> None:
    with pytest.raises(ValueError, match="YAML is empty"):
        _parse_weights_text("", source="<test>")


def test_load_weights_yaml_top_level_must_be_mapping() -> None:
    with pytest.raises(ValueError, match="must be a mapping"):
        _parse_weights_text("- 1\n- 2", source="<test>")


def test_load_weights_yaml_missing_top_level_keys() -> None:
    text = "version: v2.0\npositive_weights:\n  flow: 0.25\n  struct: 0.25\n  regime: 0.25\n  signal: 0.25\n"
    with pytest.raises(ValueError, match="penalty_caps"):
        _parse_weights_text(text, source="<test>")


def test_load_weights_yaml_missing_positive_key() -> None:
    text = (
        "version: v2.0\n"
        "positive_weights:\n  flow: 0.40\n  struct: 0.30\n  regime: 0.30\n"  # no signal
        "penalty_caps:\n  event: 0.30\n  liquidity: 0.25\n"
    )
    with pytest.raises(ValueError, match="signal"):
        _parse_weights_text(text, source="<test>")


def test_load_weights_yaml_positive_weights_not_mapping() -> None:
    text = (
        "version: v2.0\n"
        "positive_weights: 'oops, just a string'\n"
        "penalty_caps:\n  event: 0.30\n  liquidity: 0.25\n"
    )
    with pytest.raises(ValueError, match="must be a mapping"):
        _parse_weights_text(text, source="<test>")


def test_load_weights_yaml_penalty_caps_not_mapping() -> None:
    text = (
        "version: v2.0\n"
        "positive_weights:\n  flow: 0.30\n  struct: 0.25\n  regime: 0.25\n  signal: 0.20\n"
        "penalty_caps: 'oops'\n"
    )
    with pytest.raises(ValueError, match="must be a mapping"):
        _parse_weights_text(text, source="<test>")


def test_load_weights_yaml_missing_penalty_key() -> None:
    text = (
        "version: v2.0\n"
        "positive_weights:\n  flow: 0.30\n  struct: 0.25\n  regime: 0.25\n  signal: 0.20\n"
        "penalty_caps:\n  event: 0.30\n"  # missing liquidity
    )
    with pytest.raises(ValueError, match="liquidity"):
        _parse_weights_text(text, source="<test>")


def test_load_weights_yaml_non_numeric_value() -> None:
    text = (
        "version: v2.0\n"
        "positive_weights:\n  flow: 'high'\n  struct: 0.25\n  regime: 0.25\n  signal: 0.20\n"
        "penalty_caps:\n  event: 0.30\n  liquidity: 0.25\n"
    )
    with pytest.raises(ValueError, match="flow"):
        _parse_weights_text(text, source="<test>")


def test_load_weights_yaml_bool_value_rejected() -> None:
    """Booleans subclass int; reject explicitly so True doesn't become 1.0."""
    text = (
        "version: v2.0\n"
        "positive_weights:\n  flow: true\n  struct: 0.25\n  regime: 0.25\n  signal: 0.20\n"
        "penalty_caps:\n  event: 0.30\n  liquidity: 0.25\n"
    )
    with pytest.raises(ValueError, match="bool"):
        _parse_weights_text(text, source="<test>")


def test_load_weights_yaml_empty_version_rejected() -> None:
    text = (
        "version: ''\n"
        "positive_weights:\n  flow: 0.30\n  struct: 0.25\n  regime: 0.25\n  signal: 0.20\n"
        "penalty_caps:\n  event: 0.30\n  liquidity: 0.25\n"
    )
    with pytest.raises(ValueError, match="non-empty string"):
        _parse_weights_text(text, source="<test>")


def test_load_weights_yaml_sum_not_one_rejected() -> None:
    text = (
        "version: v2.0\n"
        "positive_weights:\n  flow: 0.50\n  struct: 0.50\n  regime: 0.50\n  signal: 0.50\n"
        "penalty_caps:\n  event: 0.30\n  liquidity: 0.25\n"
    )
    with pytest.raises(ValueError, match="must sum to 1.0"):
        _parse_weights_text(text, source="<test>")


def test_load_weights_yaml_forward_tolerant_unknown_top_level_key() -> None:
    """Unknown top-level keys are ignored (e.g. future metadata block)."""
    text = (
        "version: v2.0\n"
        "positive_weights:\n  flow: 0.30\n  struct: 0.25\n  regime: 0.25\n  signal: 0.20\n"
        "penalty_caps:\n  event: 0.30\n  liquidity: 0.25\n"
        "metadata:\n  author: 'engineer'\n"
    )
    w = _parse_weights_text(text, source="<test>")
    assert w.version == "v2.0"


def test_load_weights_yaml_packaged_path_resolves() -> None:
    """Loader resolves the packaged weights.yaml without relying on cwd."""
    assert _PACKAGED_WEIGHTS_PATH.exists()
    w = load_weights_yaml(_PACKAGED_WEIGHTS_PATH)
    assert w == DEFAULT_WEIGHTS


# ----------------------------------------------------------------------
# recommend() integration
# ----------------------------------------------------------------------


@pytest.fixture(scope="module")
def packaged_rules():  # type: ignore[no-untyped-def]
    return load_default_rules()


def test_recommend_populates_confidence_breakdown(packaged_rules) -> None:  # type: ignore[no-untyped-def]
    rec = recommend(
        market_state=_market_state(regime_score=0.60),
        flow_score=_flow_score(confidence=0.60, score=30),
        positions=PositionState(),
        profile=_profile(),
        rules=packaged_rules,
    )
    assert rec.confidence_breakdown is not None
    assert rec.confidence_breakdown.weights_version == "v2.0"
    # Confidence equals positive × penalty_mult (within FP epsilon)
    b = rec.confidence_breakdown
    assert rec.confidence == pytest.approx(
        b.positive_score * b.penalty_multiplier, abs=1e-12
    )


def test_recommend_default_weights_used(packaged_rules) -> None:  # type: ignore[no-untyped-def]
    """Omitting `weights=` uses DEFAULT_WEIGHTS (no I/O)."""
    rec = recommend(
        market_state=_market_state(regime_score=0.60),
        flow_score=_flow_score(confidence=0.60),
        positions=PositionState(),
        profile=_profile(),
        rules=packaged_rules,
    )
    assert rec.confidence_breakdown is not None
    assert rec.confidence_breakdown.weights_version == DEFAULT_WEIGHTS.version


def test_recommend_custom_weights_changes_confidence(packaged_rules) -> None:  # type: ignore[no-untyped-def]
    """Passing a different weights bundle yields a different confidence."""
    custom = Weights(
        version="custom-test",
        # Heavy on flow, light elsewhere.
        positive_weights=PositiveWeights(
            flow=0.90, struct=0.05, regime=0.025, signal=0.025
        ),
        penalty_caps=PenaltyCaps(event=0.0, liquidity=0.0),
    )
    base = recommend(
        market_state=_market_state(regime_score=0.20),
        flow_score=_flow_score(confidence=0.90, score=80),
        positions=PositionState(),
        profile=_profile(),
        rules=packaged_rules,
    )
    weighted = recommend(
        market_state=_market_state(regime_score=0.20),
        flow_score=_flow_score(confidence=0.90, score=80),
        positions=PositionState(),
        profile=_profile(),
        rules=packaged_rules,
        weights=custom,
    )
    assert base.confidence != weighted.confidence
    assert weighted.confidence_breakdown is not None
    assert weighted.confidence_breakdown.weights_version == "custom-test"


def test_recommend_illiquidity_penalty_flows_through(packaged_rules) -> None:  # type: ignore[no-untyped-def]
    """M1.11 plumbing: the illiquidity_penalty kwarg lowers confidence."""
    common = dict(
        market_state=_market_state(regime_score=0.60),
        flow_score=_flow_score(confidence=0.60, score=20),
        positions=PositionState(),
        profile=_profile(),
        rules=packaged_rules,
    )
    no_penalty = recommend(**common)  # type: ignore[arg-type]
    with_penalty = recommend(**common, illiquidity_penalty=1.0)  # type: ignore[arg-type]
    assert with_penalty.confidence < no_penalty.confidence
    # Liquidity cap is 0.25 → 25% reduction at penalty=1.0
    assert with_penalty.confidence == pytest.approx(
        no_penalty.confidence * 0.75, abs=1e-12
    )


def test_recommend_is_deterministic(packaged_rules) -> None:  # type: ignore[no-untyped-def]
    """Same inputs → byte-identical breakdown."""
    common = dict(
        market_state=_market_state(regime_score=0.60),
        flow_score=_flow_score(confidence=0.60, score=20),
        positions=PositionState(),
        profile=_profile(),
        rules=packaged_rules,
    )
    a = recommend(**common)  # type: ignore[arg-type]
    b = recommend(**common)  # type: ignore[arg-type]
    assert a.confidence == b.confidence
    assert a.confidence_breakdown == b.confidence_breakdown


# ----------------------------------------------------------------------
# Hypothesis property tests
# ----------------------------------------------------------------------


_floats_0_1 = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)


@settings(suppress_health_check=[HealthCheck.too_slow], deadline=None, max_examples=200)
@given(
    flow=_floats_0_1,
    struct=_floats_0_1,
    regime=_floats_0_1,
    signal=_floats_0_1,
    event=_floats_0_1,
    liquidity=_floats_0_1,
)
def test_compose_output_is_bounded(
    flow: float,
    struct: float,
    regime: float,
    signal: float,
    event: float,
    liquidity: float,
) -> None:
    """For any valid inputs, confidence ∈ [0, 1] and breakdown fields stay bounded."""
    inputs = ConfidenceInputs(
        flow_alignment=flow,
        structure_alignment=struct,
        regime_match=regime,
        signal_alignment=signal,
        event_risk_penalty=event,
        illiquidity_penalty=liquidity,
    )
    confidence, breakdown = compose(inputs, DEFAULT_WEIGHTS)
    assert 0.0 <= confidence <= 1.0
    assert 0.0 <= breakdown.positive_score <= 1.0
    assert 0.0 <= breakdown.penalty_multiplier <= 1.0


@settings(suppress_health_check=[HealthCheck.too_slow], deadline=None, max_examples=50)
@given(
    flow=_floats_0_1,
    struct=_floats_0_1,
    regime=_floats_0_1,
    signal=_floats_0_1,
)
def test_compose_is_monotone_in_positive_components(
    flow: float, struct: float, regime: float, signal: float
) -> None:
    """Increasing any positive component (with no penalties) cannot decrease confidence."""
    base = compose(
        ConfidenceInputs(
            flow_alignment=flow,
            structure_alignment=struct,
            regime_match=regime,
            signal_alignment=signal,
            event_risk_penalty=0.0,
            illiquidity_penalty=0.0,
        ),
        DEFAULT_WEIGHTS,
    )[0]
    bumped = compose(
        ConfidenceInputs(
            flow_alignment=min(flow + 0.05, 1.0),
            structure_alignment=struct,
            regime_match=regime,
            signal_alignment=signal,
            event_risk_penalty=0.0,
            illiquidity_penalty=0.0,
        ),
        DEFAULT_WEIGHTS,
    )[0]
    assert bumped >= base - 1e-12


@settings(suppress_health_check=[HealthCheck.too_slow], deadline=None, max_examples=50)
@given(event=_floats_0_1, liquidity=_floats_0_1)
def test_compose_is_antitone_in_penalties(event: float, liquidity: float) -> None:
    """Increasing a penalty (with fixed positives) cannot increase confidence."""
    fixed_positives = dict(
        flow_alignment=0.8,
        structure_alignment=0.7,
        regime_match=0.9,
        signal_alignment=0.75,
    )
    low_pen, _ = compose(
        ConfidenceInputs(
            **fixed_positives,
            event_risk_penalty=event,
            illiquidity_penalty=liquidity,
        ),
        DEFAULT_WEIGHTS,
    )
    high_pen, _ = compose(
        ConfidenceInputs(
            **fixed_positives,
            event_risk_penalty=min(event + 0.05, 1.0),
            illiquidity_penalty=liquidity,
        ),
        DEFAULT_WEIGHTS,
    )
    assert high_pen <= low_pen + 1e-12
