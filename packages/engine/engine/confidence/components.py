"""Per-component scoring functions for the Confidence Composer.

Per plan v1.2 §9.7 + §22.13, the composer accepts a `ConfidenceInputs`
bundle. These helpers turn upstream engine outputs (FlowScore,
MarketStateResult, UserStrategyProfile) into that bundle.

Each helper:

  - Is a pure function of its arguments (no I/O, no state)
  - Returns a float in `[0, 1]`
  - Documents the V1 prior used and its calibration anchors

The aggregate constructor `compute_confidence_inputs()` wires every
helper into a single `ConfidenceInputs`, taking `illiquidity_penalty`
as an explicit parameter (defaulting to `0.0`) so the M1.11 Execution
Feasibility Module can plumb a real value through later without
touching the rest of the engine.

ADR-0008 Phase 4 ML node-swap may replace any of these helpers with a
learned scorer. The contract (signature → `[0, 1]`) is the boundary —
the calibration logic inside is freely replaceable.
"""

from __future__ import annotations

from engine._utils import clip01
from engine.confidence.types import ConfidenceInputs
from engine.flow_score.types import FlowScore
from engine.market_state.classify import MarketStateResult
from engine.profiles import UserStrategyProfile

# ----------------------------------------------------------------------
# Calibration constants
# ----------------------------------------------------------------------

# Linear ramp for event_risk_penalty: 0 days → 1.0, EVENT_HORIZON_DAYS → 0.0.
# Beyond the horizon the penalty is 0 (no immediate event risk).
_EVENT_HORIZON_DAYS: float = 30.0

# Drawdown-tolerance boost: per plan §9.7 line 1553,
# "event_risk_penalty is up-weighted when drawdown_tolerance < 0.10".
# We implement the up-weight as a multiplicative bump that is then clipped.
_DRAWDOWN_BOOST_THRESHOLD: float = 0.10
_DRAWDOWN_BOOST_FACTOR: float = 1.5

# Structure-alignment blend weights. Tuned to favor trend over breakout
# (a sustained trend is a stronger structural signal than a single-bar
# breakout), with a smaller contribution from OI concentration.
_STRUCT_W_TREND: float = 0.50
_STRUCT_W_BREAKOUT: float = 0.30
_STRUCT_W_OI: float = 0.20

# Flow-alignment blend: equal parts FlowScore.confidence (OI-derived
# reliability) and magnitude of the signed score (decisiveness).
_FLOW_W_CONFIDENCE: float = 0.50
_FLOW_W_MAGNITUDE: float = 0.50

# Signal-alignment blend: equal parts regime confidence and flow
# confidence. The composite captures "do the two engines agree?"
_SIGNAL_W_REGIME: float = 0.50
_SIGNAL_W_FLOW: float = 0.50


# ----------------------------------------------------------------------
# Per-component scorers
# ----------------------------------------------------------------------


def compute_flow_alignment(flow_score: FlowScore) -> float:
    """Reliability + magnitude of the FlowScore signal.

    V1 blend:
        0.5 × flow_score.confidence
      + 0.5 × |flow_score.score| / 100

    The first term captures OI-derived reliability (already in `[0, 1]`).
    The second term captures decisiveness — a NEUTRAL flow scores 0,
    a strongly BULLISH or BEARISH flow scores near 1.

    Returns `[0, 1]`.
    """
    magnitude = abs(flow_score.score) / 100.0
    return clip01(
        _FLOW_W_CONFIDENCE * flow_score.confidence + _FLOW_W_MAGNITUDE * magnitude
    )


def compute_structure_alignment(market_state: MarketStateResult) -> float:
    """Decisiveness of market structure (trend + breakout + OI).

    V1 blend:
        0.50 × trend_strength
      + 0.30 × breakout_signal
      + 0.20 × oi_concentration_at_max_pain

    All three inputs are in `[0, 1]` (engine-canonical scale per
    `engine.market_state.classify` docstring). Higher = more decisive
    structural picture.

    Returns `[0, 1]`.
    """
    return clip01(
        _STRUCT_W_TREND * market_state.trend_strength
        + _STRUCT_W_BREAKOUT * market_state.breakout_signal
        + _STRUCT_W_OI * market_state.oi_concentration_at_max_pain
    )


def compute_regime_match(market_state: MarketStateResult) -> float:
    """Direct pass-through of the regime classifier's confidence.

    `MarketStateResult.regime_score` is already in `[0, 1]`. We clip
    defensively in case an upstream change loosens that contract.

    Returns `[0, 1]`.
    """
    return clip01(market_state.regime_score)


def compute_signal_alignment(
    market_state: MarketStateResult,
    flow_score: FlowScore,
) -> float:
    """Cross-engine agreement (regime confidence × flow confidence).

    V1 blend:
        0.5 × market_state.regime_score
      + 0.5 × flow_score.confidence

    Captures "do the two engines agree on a strong signal?". Two
    confident engines → high alignment; one weak engine drags the
    score down.

    Returns `[0, 1]`.
    """
    return clip01(
        _SIGNAL_W_REGIME * market_state.regime_score
        + _SIGNAL_W_FLOW * flow_score.confidence
    )


def compute_event_risk_penalty(
    market_state: MarketStateResult,
    profile: UserStrategyProfile,
) -> float:
    """Penalty applied for proximity to a scheduled event.

    V1 calibration (linear ramp + drawdown-tolerance boost):
      - `days_to_next_event is None`  → 0.0 (no scheduled event)
      - `days >= 30`                  → 0.0 (out of horizon)
      - `0 ≤ days < 30`               → `(30 - days) / 30`
      - Multiplied by `1.5` when `drawdown_tolerance < 0.10`
        (low-tolerance users get more aggressive event guarding,
        per plan §9.7 line 1553).
      - Result clipped to `[0, 1]`.

    Returns `[0, 1]`.
    """
    days = market_state.days_to_next_event
    if days is None:
        return 0.0
    raw = clip01(1.0 - float(days) / _EVENT_HORIZON_DAYS)
    if profile.drawdown_tolerance < _DRAWDOWN_BOOST_THRESHOLD:
        raw *= _DRAWDOWN_BOOST_FACTOR
    return clip01(raw)


def compute_illiquidity_penalty() -> float:
    """V1 stub — Execution Feasibility (M1.11) not shipped yet.

    The composer accepts `illiquidity_penalty` as a normal `[0, 1]`
    input; M1.11 will pipe a real value through `compute_confidence_inputs`
    and `recommend()`. Until then the V1 default is `0.0` (no penalty).

    Kept as a function (rather than just a constant) so M1.11 can fill
    in the body without changing the import surface.

    Returns `[0, 1]` — always `0.0` in V1.
    """
    return 0.0


# ----------------------------------------------------------------------
# Aggregate constructor
# ----------------------------------------------------------------------


def compute_confidence_inputs(
    *,
    market_state: MarketStateResult,
    flow_score: FlowScore,
    profile: UserStrategyProfile,
    illiquidity_penalty: float = 0.0,
) -> ConfidenceInputs:
    """Build the full `ConfidenceInputs` bundle from engine state.

    Used by `engine.recommendation.recommend.recommend()` and (later)
    by `engine.decision.produce_daily_decision()` (M1.13). Keeping the
    constructor centralized means changes to the component blend ripple
    through every caller automatically.

    Args:
        market_state: Output of `engine.market_state.classify`.
        flow_score: Output of `engine.flow_score.compute`.
        profile: The user's strategy profile (used by
            `compute_event_risk_penalty` for the low-tolerance boost).
        illiquidity_penalty: Optional explicit `[0, 1]` value (default
            `0.0`). M1.11 will replace this default with a value
            derived from `engine.execution.assess(...)`.

    Returns:
        A `ConfidenceInputs` instance with all six fields populated.

    Pure function (per ADR-0005).
    """
    return ConfidenceInputs(
        flow_alignment=compute_flow_alignment(flow_score),
        structure_alignment=compute_structure_alignment(market_state),
        regime_match=compute_regime_match(market_state),
        signal_alignment=compute_signal_alignment(market_state, flow_score),
        event_risk_penalty=compute_event_risk_penalty(market_state, profile),
        illiquidity_penalty=clip01(illiquidity_penalty),
    )
