"""Flow Score Engine result types.

Per plan v1.2 §9.3a (V1 LOCKED `FlowScore` contract) and §22.2 (FlowScore
schema reconciliation).

`FlowScore` is the engine output. `Bias` and `RecommendedAction` are
the locked enums for the high-level categorization that downstream
modules (Recommendation Engine, Today screen UI, Confidence Composer)
read directly.

The V1 LOCK is explicit in §22.2: subsequent ML upgrades MUST preserve
these field names and semantics. Adding fields is permitted; renaming or
removing is breaking. The Phase 4 ML node-swap (per
[ADR-0008](../decisions/0008-enhancement-adoption-roadmap.md)) replaces
the deterministic `compute()` body while leaving the `FlowScore` contract
unchanged.

The result is a frozen dataclass (following the M1.4 `MarketStateResult`
convention). When the `/engine/flow-score` endpoint lands (M1.15) the
type may migrate to a frozen Pydantic model for JSON serialization +
TypeScript codegen via `packages/shared-types/`. Field names are stable
across that migration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Bias(StrEnum):
    """High-level flow-bias categorization.

    Derived from the signed `FlowScore.score` plus the `pin_probability`
    threshold. The Recommendation Engine and Today screen UI key off
    this enum for strategy whitelisting.

    The string values are wire-stable — adding a new value requires
    coordinated changes in the API layer + Postgres enum + TS codegen.
    """

    BULLISH = "BULLISH"
    NEUTRAL = "NEUTRAL"
    BEARISH = "BEARISH"
    PIN_RISK = "PIN_RISK"


class RecommendedAction(StrEnum):
    """The action recommended by the V1 §9.3a decision tree.

    First-match-wins over the conditions in `_decide_action()`:

        score >= +40 and gamma_risk <= 0.5  → SELL_CALL_AGGRESSIVE
        score >= +10                        → SELL_CALL_PARTIAL
        score in (-10, +10) and pin>=0.6    → WAIT
        score <= -20 and gamma_risk >= 0.6  → BUY_PROTECTION
        score <= -10                        → REDUCE_COVERAGE
        otherwise                           → MONITOR
    """

    SELL_CALL_AGGRESSIVE = "SELL_CALL_AGGRESSIVE"
    SELL_CALL_PARTIAL = "SELL_CALL_PARTIAL"
    WAIT = "WAIT"
    BUY_PROTECTION = "BUY_PROTECTION"
    REDUCE_COVERAGE = "REDUCE_COVERAGE"
    MONITOR = "MONITOR"


@dataclass(frozen=True)
class FlowScore:
    """V1 LOCKED Flow Score contract (per plan §22.2 + §9.3a).

    Fields:
        score:               Signed composite in [-100, 100]
                             = bullish_score − bearish_score.
        bullish_score:       [0, 100]. 5-component weighted score per §9.3a.
        bearish_score:       [0, 100]. Symmetric 5-component score.
        bias:                BULLISH / NEUTRAL / BEARISH / PIN_RISK.
        recommended_action:  One of six actions per the §9.3a decision tree.
        pin_probability:     [0, 1]. Multiplicative blend of spot-to-max-pain,
                             opex proximity, and OI concentration at max-pain.
        gamma_risk:          [0, 1]. The `gamma_score.score` magnitude.
        gamma_sign:          {-1, 0, +1}. Dealer net short / neutral / long.
        confidence:          [0, 1]. Function of total OI in focus expiries.
        explanation:         Human-readable rationale string.
        breakdown:           Per-component breakdown of bullish/bearish
                             scores. Keys are stable: `bullish_dist`,
                             `bullish_call_vol`, `bullish_skew`,
                             `bullish_basis`, `bullish_pcrv`, plus
                             analogous bearish_* keys.

    All numeric fields are bounded as documented. The frozen dataclass is
    immutable; consumers MUST NOT mutate `breakdown` (Python frozen
    dataclasses freeze attribute assignment, not deep-mutation of dict
    contents — same convention as `*ScoreResult`).
    """

    # Composite scores
    score: float
    bullish_score: float
    bearish_score: float

    # Categorization
    bias: Bias
    recommended_action: RecommendedAction

    # Specific signals
    pin_probability: float
    gamma_risk: float
    gamma_sign: int
    confidence: float

    # Explainability
    explanation: str
    breakdown: dict[str, float] = field(default_factory=dict)
