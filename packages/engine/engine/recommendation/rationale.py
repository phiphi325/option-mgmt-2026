"""Rationale builder for the Recommendation Engine.

Per plan v1.2 §9.4 and §17 M1.7.

Produces a 2-4 sentence human-readable rationale string explaining the
recommendation. The string is **stable across patch bumps** — Today
screen UI snapshot tests, disclosure copy templates, and downstream
NLP / compliance tooling may anchor on phrases like "Recommended
strategy:" or "Market state:".

Three sentences always present:

  1. "Recommended strategy: {strategy_class} ({action})."
  2. "Market state: {regime_name} (regime score {regime_score:.2f})."
  3. "Flow context: score {score:+.1f}, bias {bias}."

One optional fourth sentence when the recommendation was downgraded or
overridden by the regime/profile mapping:

  4. "{downgrade reason} — strategy adjusted from {original}."

Pure function (per ADR-0005). No I/O.
"""

from __future__ import annotations

from engine.flow_score.types import FlowScore
from engine.market_state.classify import MarketStateResult
from engine.recommendation.types import StrategyClass


def render_rationale(
    *,
    strategy_class: StrategyClass,
    market_state: MarketStateResult,
    flow_score: FlowScore,
    downgrade_reason: str | None = None,
    original_strategy: StrategyClass | None = None,
) -> str:
    """Build the rationale string for a `Recommendation`.

    Args:
        strategy_class: The final selected strategy class.
        market_state: Source `MarketStateResult` (for regime context).
        flow_score: Source `FlowScore` (for action / score / bias).
        downgrade_reason: When non-`None`, the regime or profile rule
            that overrode the natural strategy mapping. Triggers the
            optional fourth sentence.
        original_strategy: The strategy class that *would* have been
            selected if the downgrade rule had not fired. Required when
            `downgrade_reason` is provided.

    Returns:
        2-4 sentence space-joined rationale string.
    """
    sentences: list[str] = []

    # Sentence 1: strategy + action
    sentences.append(
        f"Recommended strategy: {strategy_class.value} "
        f"({flow_score.recommended_action.value} per FlowScore §9.3a)."
    )

    # Sentence 2: market state
    sentences.append(
        f"Market state: {market_state.regime.value} "
        f"(regime score {market_state.regime_score:.2f})."
    )

    # Sentence 3: flow context
    sentences.append(
        f"Flow context: score {flow_score.score:+.1f}, bias {flow_score.bias.value}."
    )

    # Sentence 4 (optional): downgrade explanation
    if downgrade_reason is not None and original_strategy is not None:
        sentences.append(
            f"{downgrade_reason} — strategy adjusted from {original_strategy.value}."
        )

    return " ".join(sentences)


# Re-export for documentation / introspection. The standard set of
# downgrade reason strings is shipped here so the orchestrator and tests
# can reference them by name without typo risk.

DOWNGRADE_REASON_HIGH_IV_EVENT: str = (
    "Event-elevated IV — gamma/vega risk argues against aggressive premium sale"
)
DOWNGRADE_REASON_HIGH_IV_PIN: str = (
    "Pin-risk regime — directional bets are noisy near max pain"
)
DOWNGRADE_REASON_LOW_IV_TREND: str = (
    "Low-IV trend — premium is cheap; partial coverage better than aggressive"
)
DOWNGRADE_REASON_BREAKOUT: str = (
    "Breakout regime — avoid capping upside with aggressive call sale"
)
DOWNGRADE_REASON_POST_EVENT_REPRICE: str = (
    "Post-event reprice — recent dislocation; monitor before committing"
)
DOWNGRADE_REASON_CONSERVATIVE_PROFILE: str = (
    "Conservative profile — downgrading aggressive sizing"
)
DOWNGRADE_REASON_IV_RANK_GATE: str = (
    "IV rank below profile threshold — premium-selling unattractive"
)
DOWNGRADE_REASON_COLLAR_PREFERENCE: str = (
    "Profile prefers collars — pairing protective put with a call sale"
)


__all__ = [
    "DOWNGRADE_REASON_BREAKOUT",
    "DOWNGRADE_REASON_COLLAR_PREFERENCE",
    "DOWNGRADE_REASON_CONSERVATIVE_PROFILE",
    "DOWNGRADE_REASON_HIGH_IV_EVENT",
    "DOWNGRADE_REASON_HIGH_IV_PIN",
    "DOWNGRADE_REASON_IV_RANK_GATE",
    "DOWNGRADE_REASON_LOW_IV_TREND",
    "DOWNGRADE_REASON_POST_EVENT_REPRICE",
    "render_rationale",
]
