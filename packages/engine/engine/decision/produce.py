"""Master Decision Engine — `produce_daily_decision()`.

Per plan v1.2 §9.6 + §17 M1.13.

Wires together every upstream engine into a single `DailyDecision`:

    classify()        → MarketStateResult     [M1.4]   (caller-provided)
    compute()         → FlowScore             [M1.5b]  (caller-provided)
    recommend()       → RecommendationResult  [M1.9]
    select_strikes()  → StrikeSelection       [M1.7]
    downgrade_if_…()  → DowngradeResult       [M1.12]  (wraps select+assess)
    compose()         → final confidence      [M1.10]

Why M1.13 takes `market_state` + `flow_score` as inputs rather than
running `classify()` + `compute()` itself: those entry points have
many-input signatures (classify has 18 inputs per §22.3 — `iv_rank`,
`iv_percentile`, `hv_30`, etc.) that the API layer in `apps/api` is
already hydrating from Postgres. Threading 20+ arguments through the
Master Decision Engine adds nothing the API doesn't already track. The
API layer composes upstream engines; M1.13 stitches their results
together.

Pipeline (single-pass with downgrade feedback):

  1. Call `recommend()` with `illiquidity_penalty=0.0` to produce
     a tentative `RecommendationResult`. The rule selection (including
     the `confidence_lte:` clause on `hold_no_op`) uses the pre-execution
     view of confidence.
  2. For each emitted action, call `downgrade_if_needed()` — which
     runs `select_strikes()`, `assess()`, and the M1.12 escalation
     ladder. Collect per-action `DowngradeResult`s.
  3. Compute the aggregate `illiquidity_penalty` across all actions
     (max over per-action `liquidity_penalty(final_execution)`). For
     a 0-action recommendation (NO_OP / REDUCE_COVERAGE without legs),
     the aggregate is 0.0 — no fill risk.
  4. Re-run `compose()` with the real `illiquidity_penalty` → produce
     the FINAL `(confidence, ConfidenceBreakdown)`. This replaces
     `recommendation.confidence` / `recommendation.confidence_breakdown`
     on the persisted `DailyDecision`.
  5. Stamp `inputs_hash` + `engine_version` + `weights_version`; gather
     the `escalated` flag (True iff any downgrade escalated); assemble
     `DailyDecision`.

The two-stage compose() is the explicit cost of decoupling rule
selection from execution feasibility — M1.12 / M1.13 know fill quality;
M1.9's rule pipeline knows it earlier and would need to re-evaluate.
We accept that the rule (which action) is selected on the pre-execution
view; the confidence number reflects the post-execution view. The plan
§9.6 pseudocode follows the same pattern.

Pure function per ADR-0005 — no I/O, no clock, no env. The decision
id is generated deterministically from the inputs hash so identical
inputs produce identical `DailyDecision`s (replay-safe).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from engine.confidence import (
    DEFAULT_WEIGHTS,
    Weights,
    compose,
    compute_confidence_inputs,
)
from engine.decision.hashing import compute_inputs_hash
from engine.decision.types import DailyDecision
from engine.execution import (
    Execution,
    OrderType,
    downgrade_if_needed,
    liquidity_penalty,
)
from engine.execution.downgrade import DowngradeResult
from engine.flow_score.types import FlowScore
from engine.market_state.classify import MarketStateResult
from engine.profiles import UserStrategyProfile
from engine.recommendation import (
    PositionState,
    RecommendationResult,
    RuleSpec,
    recommend,
)
from engine.recommendation.yaml_loader import load_default_rules
from engine.strike_selector.types import StrikeSelection
from engine.types import ChainSnapshot
from engine.version import __version__ as _engine_version

# Canonical V1 disclaimer set per plan §15. The API layer may augment
# this (e.g. broker-specific risk text) but the engine's contribution
# is fixed.
DEFAULT_DISCLAIMERS: tuple[str, ...] = (
    "Educational only",
    "Not financial advice",
    "Verify with broker",
)


def produce_daily_decision(
    *,
    as_of: datetime,
    ticker: str,
    chain_snapshot: ChainSnapshot,
    positions: PositionState,
    profile: UserStrategyProfile,
    market_state: MarketStateResult,
    flow_score: FlowScore,
    rules: Sequence[RuleSpec] | None = None,
    weights: Weights | None = None,
    risk_free_rate: float = 0.05,
    dividend_yield: float = 0.0,
    data_freshness: Sequence[tuple[str, int | float | bool]] = (),
    disclaimers: Sequence[str] = DEFAULT_DISCLAIMERS,
) -> DailyDecision:
    """V1 Master Decision Engine entry point per plan §9.6.

    Args:
        as_of:           Decision-time timestamp.
        ticker:          Underlying symbol (MSFT-only in V1).
        chain_snapshot:  Frozen `ChainSnapshot` (input to downstream engines).
        positions:       Current option positions.
        profile:         User's strategy profile snapshot.
        market_state:    Pre-computed `MarketStateResult` from
                         `engine.market_state.classify`.
        flow_score:      Pre-computed `FlowScore` from
                         `engine.flow_score.compute`.
        rules:           Sequence of `RuleSpec`s. Defaults to the packaged
                         V1 rules via `load_default_rules()`.
        weights:         Confidence Composer weights. Defaults to
                         `engine.confidence.DEFAULT_WEIGHTS`.
        risk_free_rate:  BS pricing input for `select_strikes` /
                         downgrade ladder. Default `0.05`.
        dividend_yield:  BS pricing input. Default `0.0`.
        data_freshness:  Tuple of (key, value) pairs describing input
                         staleness; passed through to `DailyDecision.data_freshness`.
                         The engine doesn't compute these — the API hydrates them.
        disclaimers:     Disclaimer strings echoed onto the decision.
                         Default is `DEFAULT_DISCLAIMERS`.

    Returns:
        `DailyDecision` (frozen dataclass) with the full V1 payload.

    Pure function (per ADR-0005). Same inputs → byte-identical output.
    """
    effective_rules = rules if rules is not None else load_default_rules()
    effective_weights = weights if weights is not None else DEFAULT_WEIGHTS

    # ------------------------------------------------------------------
    # Stage 1: tentative recommendation with no illiquidity penalty.
    # ------------------------------------------------------------------
    tentative_rec: RecommendationResult = recommend(
        market_state=market_state,
        flow_score=flow_score,
        positions=positions,
        profile=profile,
        rules=effective_rules,
        weights=effective_weights,
        illiquidity_penalty=0.0,
    )

    # ------------------------------------------------------------------
    # Stage 2: per-action strike selection + execution feasibility +
    # downgrade ladder.
    # ------------------------------------------------------------------
    downgrades: list[DowngradeResult] = []
    selections: list[StrikeSelection] = []
    executions: list[Execution] = []
    aggregate_penalty = 0.0

    for action in tentative_rec.actions:
        dr = downgrade_if_needed(
            action=action,
            chain_snapshot=chain_snapshot,
            risk_free_rate=risk_free_rate,
            dividend_yield=dividend_yield,
        )
        downgrades.append(dr)
        selections.append(dr.final_selection)
        executions.append(dr.final_execution)
        penalty = liquidity_penalty(dr.final_execution)
        if penalty > aggregate_penalty:
            aggregate_penalty = penalty

    escalated = any(dr.escalated for dr in downgrades)

    # ------------------------------------------------------------------
    # Stage 3: final confidence with the post-downgrade illiquidity penalty.
    # ------------------------------------------------------------------
    final_inputs = compute_confidence_inputs(
        market_state=market_state,
        flow_score=flow_score,
        profile=profile,
        illiquidity_penalty=aggregate_penalty,
    )
    final_confidence, final_breakdown = compose(final_inputs, effective_weights)

    # ------------------------------------------------------------------
    # Stage 4: stamping + assembly.
    # ------------------------------------------------------------------
    inputs_hash = compute_inputs_hash(
        as_of=as_of,
        ticker=ticker,
        chain_snapshot=chain_snapshot,
        positions=positions,
        profile=profile,
        market_state=market_state,
        flow_score=flow_score,
    )
    # decision_id is derived from inputs_hash + as_of so identical inputs
    # produce identical decisions (replay-safe). Strip the "sha256:" prefix
    # and use the first 12 hex chars + as_of timestamp suffix for a
    # human-readable id that's still globally unique.
    decision_id = f"dd_{inputs_hash.split(':', 1)[1][:12]}_{int(as_of.timestamp())}"

    return DailyDecision(
        decision_id=decision_id,
        as_of=as_of,
        ticker=ticker,
        spot=chain_snapshot.spot,
        user_profile_snapshot=profile,
        market_state=market_state,
        flow_score=flow_score,
        recommendation=tentative_rec,
        strike_selections=tuple(selections),
        downgrades=tuple(downgrades),
        executions=tuple(executions),
        confidence=final_confidence,
        confidence_breakdown=final_breakdown,
        inputs_hash=inputs_hash,
        engine_version=_engine_version,
        weights_version=effective_weights.version,
        data_freshness=tuple(data_freshness),
        disclaimers=tuple(disclaimers),
        escalated=escalated,
    )


# Re-export the engine version + the OrderType (so downstream API code
# can import everything it needs from `engine.decision`).
__all__ = [
    "DEFAULT_DISCLAIMERS",
    "OrderType",
    "produce_daily_decision",
]
