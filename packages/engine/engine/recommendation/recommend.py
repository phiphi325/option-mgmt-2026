"""Recommendation Engine — V1 `recommend()` orchestrator.

Per plan v1.2 §9.4 (Recommendation Engine) and §17 M1.7.

`recommend()` consumes the upstream Market State Engine + Flow Score
Engine + User Strategy Profile and produces a concrete `Recommendation`:
strategy class, parameters, composite confidence, rationale, and
warnings.

## Decision flow

  1. Map `FlowScore.recommended_action` → base `StrategyClass`.
  2. Apply regime overrides (some regimes downgrade aggressive plays).
  3. Apply user-profile overrides (conservative → downgrade;
     collar-preference → swap PROTECTIVE_PUT for COLLAR).
  4. Apply min-IV-rank gate for short-premium strategies.
  5. Compose confidence = `flow_score.confidence × regime_score`.
  6. Generate downstream parameters (target_dte, target_delta,
     size_pct, urgency_days).
  7. Build rationale string.
  8. Build warnings tuple.

## V1 calibration

Regime × action → strategy mapping lives in this module as Python
constants. ADR-0008 plans to move the rules to
`apps/api/app/config/rules.yaml` in Phase 1.5 so they can be hot-swapped
without engine version bumps. V1 keeps the rules in-engine for
simplicity and to anchor the contract.

## Confidence

V1 composite confidence is a simple multiplicative blend:

    composite = flow_score.confidence × regime_score

The M1.10 Confidence Composer (per ADR-0003) will replace this with a
weighted blend across all four scoring primitives + the flow score +
the regime confidence. Until then, this two-engine blend is the
conservative V1 baseline.

Pure function (per ADR-0005). No I/O. No DB. No clock. No env.
"""

from __future__ import annotations

from engine._utils import clip01
from engine.flow_score.types import FlowScore, RecommendedAction
from engine.market_state.classify import MarketStateResult
from engine.profiles import RiskTolerance, UserStrategyProfile
from engine.recommendation.rationale import (
    DOWNGRADE_REASON_BREAKOUT,
    DOWNGRADE_REASON_COLLAR_PREFERENCE,
    DOWNGRADE_REASON_CONSERVATIVE_PROFILE,
    DOWNGRADE_REASON_HIGH_IV_EVENT,
    DOWNGRADE_REASON_HIGH_IV_PIN,
    DOWNGRADE_REASON_IV_RANK_GATE,
    DOWNGRADE_REASON_LOW_IV_TREND,
    DOWNGRADE_REASON_POST_EVENT_REPRICE,
    render_rationale,
)
from engine.recommendation.types import Recommendation, StrategyClass
from engine.recommendation.warnings import build_warnings, is_short_premium_action
from engine.regimes import Regime

# ----------------------------------------------------------------------
# Strategy parameters per class (V1 priors)
# ----------------------------------------------------------------------
#
# These are forward-looking defaults the M1.8 Strike Selector and M1.11a
# Collar Builder consume. They are NOT user-facing; the user sees only
# the strategy class and the rationale.
#
# - target_dte:    days to expiry for the new option leg
# - target_delta:  absolute delta of the new option leg
# - size_pct:      fraction of the underlying position to act on
# - urgency_days:  rough days-to-act window (1 = today; 5 = this week;
#                  21 = this month; 100 = monitor)
#
# Phase 4 ML may learn these from realized P&L per ADR-0008.

_PARAMETERS: dict[StrategyClass, dict[str, float]] = {
    StrategyClass.COVERED_CALL_AGGRESSIVE: {
        "target_dte": 30.0,
        "target_delta": 0.25,  # OTM call
        "size_pct": 0.50,
        "urgency_days": 5.0,
    },
    StrategyClass.COVERED_CALL_PARTIAL: {
        "target_dte": 30.0,
        "target_delta": 0.35,  # closer to ATM
        "size_pct": 0.30,
        "urgency_days": 5.0,
    },
    StrategyClass.PROTECTIVE_PUT: {
        "target_dte": 60.0,
        "target_delta": 0.25,  # OTM put
        "size_pct": 1.00,  # full coverage
        "urgency_days": 1.0,  # protective decision is urgent
    },
    StrategyClass.COLLAR: {
        "target_dte": 45.0,  # compromise between call + put DTEs
        "target_delta": 0.25,  # symmetric OTM call + put
        "size_pct": 0.75,
        "urgency_days": 5.0,
    },
    StrategyClass.REDUCE_CALL_COVERAGE: {
        "target_dte": 0.0,  # close existing
        "target_delta": 0.0,
        "size_pct": 1.00,
        "urgency_days": 1.0,
    },
    StrategyClass.WAIT: {},
    StrategyClass.MONITOR: {},
}


# ----------------------------------------------------------------------
# Regimes that downgrade SELL_CALL_AGGRESSIVE
# ----------------------------------------------------------------------
#
# Per the §9.4 V1 rules:
#
#   HIGH_IV_EVENT     → COVERED_CALL_PARTIAL  (event uncertainty)
#   HIGH_IV_PIN       → WAIT                  (pin distorts directional bets)
#   LOW_IV_TREND      → COVERED_CALL_PARTIAL  (premium too cheap to aggressive)
#   BREAKOUT          → COVERED_CALL_PARTIAL  (don't cap upside on breakout)
#   POST_EVENT_REPRICE → MONITOR              (recent dislocation; observe)
#   LOW_IV_RANGE      → COVERED_CALL_AGGRESSIVE (clean environment)

_AGGRESSIVE_DOWNGRADE_MAP: dict[Regime, tuple[StrategyClass, str]] = {
    Regime.HIGH_IV_EVENT: (StrategyClass.COVERED_CALL_PARTIAL, DOWNGRADE_REASON_HIGH_IV_EVENT),
    Regime.HIGH_IV_PIN: (StrategyClass.WAIT, DOWNGRADE_REASON_HIGH_IV_PIN),
    Regime.LOW_IV_TREND: (StrategyClass.COVERED_CALL_PARTIAL, DOWNGRADE_REASON_LOW_IV_TREND),
    Regime.BREAKOUT: (StrategyClass.COVERED_CALL_PARTIAL, DOWNGRADE_REASON_BREAKOUT),
    Regime.POST_EVENT_REPRICE: (StrategyClass.MONITOR, DOWNGRADE_REASON_POST_EVENT_REPRICE),
}


# Regimes that downgrade SELL_CALL_PARTIAL — strictly a subset of the
# aggressive-downgrade rules because the recommendation is already
# conservative.
_PARTIAL_DOWNGRADE_MAP: dict[Regime, tuple[StrategyClass, str]] = {
    Regime.HIGH_IV_PIN: (StrategyClass.WAIT, DOWNGRADE_REASON_HIGH_IV_PIN),
    Regime.POST_EVENT_REPRICE: (StrategyClass.MONITOR, DOWNGRADE_REASON_POST_EVENT_REPRICE),
}


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _base_strategy(
    *,
    action: RecommendedAction,
    user_profile: UserStrategyProfile,
) -> StrategyClass:
    """Map `RecommendedAction` to the natural `StrategyClass` (pre-overrides)."""
    if action is RecommendedAction.SELL_CALL_AGGRESSIVE:
        return StrategyClass.COVERED_CALL_AGGRESSIVE
    if action is RecommendedAction.SELL_CALL_PARTIAL:
        return StrategyClass.COVERED_CALL_PARTIAL
    if action is RecommendedAction.BUY_PROTECTION:
        # Collar preference is user-configurable in the profile.
        if user_profile.prefer_collars_over_covered_calls:
            return StrategyClass.COLLAR
        return StrategyClass.PROTECTIVE_PUT
    if action is RecommendedAction.REDUCE_COVERAGE:
        return StrategyClass.REDUCE_CALL_COVERAGE
    if action is RecommendedAction.WAIT:
        return StrategyClass.WAIT
    # RecommendedAction.MONITOR — the catch-all
    return StrategyClass.MONITOR


def _apply_regime_override(
    *,
    base: StrategyClass,
    action: RecommendedAction,
    regime: Regime,
) -> tuple[StrategyClass, str | None]:
    """Apply regime-based downgrade rules.

    Returns:
        (new_strategy, downgrade_reason_or_None).
    """
    if action is RecommendedAction.SELL_CALL_AGGRESSIVE:
        if regime in _AGGRESSIVE_DOWNGRADE_MAP:
            new_strategy, reason = _AGGRESSIVE_DOWNGRADE_MAP[regime]
            return new_strategy, reason
    if action is RecommendedAction.SELL_CALL_PARTIAL:
        if regime in _PARTIAL_DOWNGRADE_MAP:
            new_strategy, reason = _PARTIAL_DOWNGRADE_MAP[regime]
            return new_strategy, reason
    # BUY_PROTECTION / REDUCE_COVERAGE / WAIT / MONITOR have no
    # regime-based downgrade in V1.
    return base, None


def _apply_profile_override(
    *,
    strategy: StrategyClass,
    user_profile: UserStrategyProfile,
) -> tuple[StrategyClass, str | None]:
    """Apply user-profile downgrade rules.

    V1 rule: CONSERVATIVE risk tolerance + AGGRESSIVE strategy →
    downgrade to PARTIAL. Other axes are surfaced via the IV-rank gate
    in `_apply_iv_rank_gate` and the collar preference in `_base_strategy`.
    """
    if (
        user_profile.risk_tolerance is RiskTolerance.CONSERVATIVE
        and strategy is StrategyClass.COVERED_CALL_AGGRESSIVE
    ):
        return StrategyClass.COVERED_CALL_PARTIAL, DOWNGRADE_REASON_CONSERVATIVE_PROFILE
    return strategy, None


def _apply_iv_rank_gate(
    *,
    strategy: StrategyClass,
    action: RecommendedAction,
    market_state: MarketStateResult,
    user_profile: UserStrategyProfile,
) -> tuple[StrategyClass, str | None]:
    """Veto short-premium strategies when IV rank is below user threshold.

    Note `market_state.iv_rank` is a fraction in `[0, 1]` (0.55 = 55th
    percentile) while `user_profile.min_iv_rank_for_short_premium` is
    an integer in `[0, 100]`. We compare on the 0-100 scale.
    """
    if (
        is_short_premium_action(action)
        and market_state.iv_rank * 100.0 < user_profile.min_iv_rank_for_short_premium
    ):
        return StrategyClass.MONITOR, DOWNGRADE_REASON_IV_RANK_GATE
    return strategy, None


def _composite_confidence(
    *,
    flow_score: FlowScore,
    market_state: MarketStateResult,
) -> float:
    """V1 multiplicative two-engine confidence blend.

    `composite = flow_score.confidence × regime_score`

    Both factors live in `[0, 1]`; the product is in `[0, 1]`. M1.10
    Composer will replace this with a richer multi-engine blend per
    ADR-0003.
    """
    return clip01(flow_score.confidence * market_state.regime_score)


# ----------------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------------


def recommend(
    *,
    market_state: MarketStateResult,
    flow_score: FlowScore,
    user_profile: UserStrategyProfile,
) -> Recommendation:
    """V1 Recommendation Engine `recommend()` per plan §9.4.

    Args:
        market_state: Upstream `MarketStateResult` from
            `engine.market_state.classify`.
        flow_score: Upstream `FlowScore` from
            `engine.flow_score.compute`.
        user_profile: User strategy profile (risk tolerance, income
            need, IV-rank threshold, collar preference).

    Returns:
        Frozen `Recommendation` with the full V1 contract.

    The function is pure (per ADR-0005) — same inputs → byte-identical
    output.

    Step-by-step:
      1. Map `flow_score.recommended_action` → natural strategy class.
      2. Apply regime-based downgrade rules.
      3. Apply user-profile downgrade rules.
      4. Apply IV-rank gate (vetoes premium-selling when IV is too low).
      5. Compute composite confidence (V1: flow × regime).
      6. Generate parameters dict for downstream Strike Selector /
         Collar Builder.
      7. Build rationale + warnings.

    Only the FIRST downgrade reason is surfaced in the rationale. This
    keeps the explanation focused on the dominant decision rule.
    Subsequent overrides still apply silently to the strategy class.
    """
    action = flow_score.recommended_action
    regime = market_state.regime

    # 1. Base strategy from the action enum
    natural = _base_strategy(action=action, user_profile=user_profile)

    # 2. Regime override
    after_regime, regime_reason = _apply_regime_override(
        base=natural, action=action, regime=regime
    )

    # 3. Profile override (currently the CONSERVATIVE → downgrade rule)
    after_profile, profile_reason = _apply_profile_override(
        strategy=after_regime, user_profile=user_profile
    )

    # 4. IV-rank gate (only fires for short-premium actions)
    after_gate, gate_reason = _apply_iv_rank_gate(
        strategy=after_profile,
        action=action,
        market_state=market_state,
        user_profile=user_profile,
    )

    # The natural-or-collar-swap reason is tracked separately to support
    # COLLAR preference traceability in the rationale.
    natural_or_collar_reason: str | None = None
    if (
        action is RecommendedAction.BUY_PROTECTION
        and user_profile.prefer_collars_over_covered_calls
    ):
        natural_or_collar_reason = DOWNGRADE_REASON_COLLAR_PREFERENCE

    # First-applied reason wins for the rationale. Order matches the
    # decision pipeline.
    downgrade_reason = (
        regime_reason or profile_reason or gate_reason or natural_or_collar_reason
    )
    original_strategy = natural if downgrade_reason else None

    final_strategy = after_gate

    # 5. Composite confidence
    confidence = _composite_confidence(
        flow_score=flow_score, market_state=market_state
    )

    # 6. Parameters
    parameters = dict(_PARAMETERS[final_strategy])

    # 7. Rationale + warnings
    rationale = render_rationale(
        strategy_class=final_strategy,
        market_state=market_state,
        flow_score=flow_score,
        downgrade_reason=downgrade_reason,
        original_strategy=original_strategy,
    )
    warnings = build_warnings(
        market_state=market_state,
        flow_score=flow_score,
        user_profile=user_profile,
    )

    return Recommendation(
        strategy_class=final_strategy,
        action=action,
        regime=regime,
        confidence=confidence,
        rationale=rationale,
        warnings=warnings,
        parameters=parameters,
    )
