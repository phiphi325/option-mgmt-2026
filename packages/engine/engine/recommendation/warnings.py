"""Warning generator for the Recommendation Engine.

Per plan v1.2 §9.4 and §17 M1.7.

Generates a tuple of human-readable warning strings keyed off the
upstream engine state. The strings are **stable across patch bumps** —
UI components and downstream NLP / compliance templates may match on
substrings like "Low confidence" or "Event window".

Pure function (per ADR-0005). No I/O. Depends only on
`engine.market_state.classify.MarketStateResult` and
`engine.flow_score.FlowScore`.
"""

from __future__ import annotations

from engine.flow_score.types import FlowScore, RecommendedAction
from engine.market_state.classify import MarketStateResult
from engine.profiles import UserStrategyProfile

# Confidence below this value triggers the low-confidence warning. Matches
# the practical "Composer multiplicative chain effectively flatlines"
# regime per the M1.5b tutorial Exercise 6 — anything under ~0.20 is
# noisy enough to warn about.
_LOW_CONFIDENCE_THRESHOLD: float = 0.20

# Event-proximity threshold. Within 7 calendar days of a scheduled event
# (earnings, FOMC, etc.) the strategy's gamma/vega risk profile changes
# materially.
_EVENT_WINDOW_DAYS: int = 7

# Opex-proximity threshold. Within 3 trading days of monthly opex,
# short-gamma positions are exposed to pinning + assignment risk.
_OPEX_PROXIMITY_DAYS: int = 3

# Gamma-amplifier threshold. `gamma_sign == -1` AND `gamma_risk >= 0.5`
# means dealers are net short gamma at meaningful magnitude — they hedge
# in the direction of spot, amplifying realized vol.
_GAMMA_AMPLIFIER_MAGNITUDE: float = 0.5

# Borderline-score band. |score| < this value means the bullish/bearish
# bias is weak; the recommendation may flip on small perturbations.
_BORDERLINE_SCORE_BAND: float = 15.0

# Actions that consume short-premium economics (calls sold > calls
# bought). For these, the IV-rank gate from `user_profile` applies.
_SHORT_PREMIUM_ACTIONS: frozenset[RecommendedAction] = frozenset(
    {
        RecommendedAction.SELL_CALL_AGGRESSIVE,
        RecommendedAction.SELL_CALL_PARTIAL,
    }
)


def build_warnings(
    *,
    market_state: MarketStateResult,
    flow_score: FlowScore,
    user_profile: UserStrategyProfile,
) -> tuple[str, ...]:
    """Compose the warnings tuple for a recommendation.

    Each condition produces at most one warning string. Order is stable
    so UI rendering doesn't shuffle between runs:

      1. Low confidence
      2. Event window
      3. Opex proximity
      4. Dealer gamma amplifier
      5. Borderline score
      6. IV rank below user threshold (short-premium actions only)

    Returns:
        Tuple of zero or more warning strings.
    """
    out: list[str] = []

    # 1. Low confidence
    if flow_score.confidence < _LOW_CONFIDENCE_THRESHOLD:
        out.append(
            f"Low confidence ({flow_score.confidence:.2f}) — focus expiry has minimal OI"
        )

    # 2. Event window
    if (
        market_state.days_to_next_event is not None
        and market_state.days_to_next_event <= _EVENT_WINDOW_DAYS
    ):
        kind = market_state.next_event_kind or "event"
        out.append(
            f"Event window — {kind} in {market_state.days_to_next_event} days; gamma/vega risk elevated"
        )

    # 3. Opex proximity
    if (
        market_state.days_to_nearest_opex is not None
        and 0 <= market_state.days_to_nearest_opex <= _OPEX_PROXIMITY_DAYS
    ):
        out.append(
            f"Opex proximity — monthly expiry in {market_state.days_to_nearest_opex} trading days"
        )

    # 4. Dealer gamma amplifier
    if (
        flow_score.gamma_sign == -1
        and flow_score.gamma_risk >= _GAMMA_AMPLIFIER_MAGNITUDE
    ):
        out.append(
            f"Dealer gamma amplifier (magnitude {flow_score.gamma_risk:.2f}) — vol expansion risk"
        )

    # 5. Borderline score
    if abs(flow_score.score) < _BORDERLINE_SCORE_BAND:
        out.append(
            f"Borderline FlowScore ({flow_score.score:+.1f}) — consider waiting for clearer signal"
        )

    # 6. IV rank below user's short-premium threshold. Note `iv_rank`
    # is a fraction in `[0, 1]` (0.55 = 55th percentile) while
    # `min_iv_rank_for_short_premium` is an integer in `[0, 100]`
    # (`50` = 50th percentile). Convert to the same scale before
    # comparing.
    if (
        flow_score.recommended_action in _SHORT_PREMIUM_ACTIONS
        and market_state.iv_rank * 100.0 < user_profile.min_iv_rank_for_short_premium
    ):
        out.append(
            f"IV rank ({int(round(market_state.iv_rank * 100))}) below your short-premium threshold "
            f"({user_profile.min_iv_rank_for_short_premium})"
        )

    return tuple(out)


def is_short_premium_action(action: RecommendedAction) -> bool:
    """Public helper: is this action a premium-selling action?

    Exposed for tests and for the orchestrator's IV-rank gate logic.
    """
    return action in _SHORT_PREMIUM_ACTIONS


__all__ = ["build_warnings", "is_short_premium_action"]


# Re-export the constants for downstream tooling / introspection. Kept
# as module attributes (not in __all__) so they are not part of the
# public API but are accessible via `engine.recommendation.warnings.LOW_CONFIDENCE_THRESHOLD`.
LOW_CONFIDENCE_THRESHOLD: float = _LOW_CONFIDENCE_THRESHOLD
EVENT_WINDOW_DAYS: int = _EVENT_WINDOW_DAYS
OPEX_PROXIMITY_DAYS: int = _OPEX_PROXIMITY_DAYS
GAMMA_AMPLIFIER_MAGNITUDE: float = _GAMMA_AMPLIFIER_MAGNITUDE
BORDERLINE_SCORE_BAND: float = _BORDERLINE_SCORE_BAND
SHORT_PREMIUM_ACTIONS: frozenset[RecommendedAction] = _SHORT_PREMIUM_ACTIONS
