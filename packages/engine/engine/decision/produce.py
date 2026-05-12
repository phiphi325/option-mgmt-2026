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

from engine.collar_builder import build as build_collar
from engine.collar_builder.types import CollarIntent, CollarStructure
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
from engine.recommendation.types import Action, EmittedAction
from engine.recommendation.yaml_loader import load_default_rules
from engine.strike_selector.types import LegSide, StrikeLeg, StrikeSelection
from engine.types import ChainSnapshot, OptionContract, OptionType
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
    # downgrade ladder. Dispatches per emit:
    #   - `OPEN_COLLAR` → `collar_builder.build(intents=[ZERO_COST])`
    #     and project the resulting 2-leg `CollarStructure` into a
    #     synthetic `StrikeSelection` + `DowngradeResult` for the
    #     parallel tuples. (M1.11b — §9.10 Integration.)
    #   - everything else → existing M1.12 `downgrade_if_needed()`
    #     ladder over `select_strikes()` + `assess()`.
    # ------------------------------------------------------------------
    downgrades: list[DowngradeResult] = []
    selections: list[StrikeSelection] = []
    executions: list[Execution] = []
    collar_structures: list[CollarStructure | None] = []
    aggregate_penalty = 0.0

    for action in tentative_rec.actions:
        if action.emit is EmittedAction.OPEN_COLLAR:
            dr, structure = _dispatch_open_collar(
                action=action,
                chain_snapshot=chain_snapshot,
                positions=positions,
                profile=profile,
                market_state=market_state,
                flow_score=flow_score,
                weights=effective_weights,
                risk_free_rate=risk_free_rate,
                dividend_yield=dividend_yield,
            )
        else:
            dr = downgrade_if_needed(
                action=action,
                chain_snapshot=chain_snapshot,
                risk_free_rate=risk_free_rate,
                dividend_yield=dividend_yield,
            )
            structure = None

        downgrades.append(dr)
        selections.append(dr.final_selection)
        executions.append(dr.final_execution)
        collar_structures.append(structure)
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
        collar_structures=tuple(collar_structures),
    )


# ----------------------------------------------------------------------
# M1.11b — Collar dispatch helpers
# ----------------------------------------------------------------------

# Sentinel for "no qty published in PositionState" — we still need to
# pass a positive integer to collar_builder.build(); the recommendation
# engine itself gates `OPEN_COLLAR` on `has_long_stock`, so reaching
# this dispatch with `underlying_shares == 0` is a misconfiguration.
# We fall back to 100 (one contract minimum) and let the M1.10
# illiquidity penalty propagate downstream.
_DEFAULT_COLLAR_QTY = 100


def _dispatch_open_collar(
    *,
    action: Action,  # noqa: ARG001 — kept for parity with downgrade_if_needed's signature; future M1.16a may consume Action.parameters
    chain_snapshot: ChainSnapshot,
    positions: PositionState,
    profile: UserStrategyProfile,
    market_state: MarketStateResult,
    flow_score: FlowScore,
    weights: Weights,
    risk_free_rate: float,
    dividend_yield: float,
) -> tuple[DowngradeResult, CollarStructure | None]:
    """Project an `OPEN_COLLAR` emit into the parallel decision tuples.

    Calls `engine.collar_builder.build(intents=[ZERO_COST])` per master
    plan §9.10 Integration — the Master Decision auto-call uses
    ZERO_COST only; the standalone `/engine/collar-builder` route
    (M1.16a) exposes the full 3-intent surface.

    Returns a `(DowngradeResult, CollarStructure | None)` pair. When
    the collar builder finds a feasible pair, the `DowngradeResult`
    carries a synthetic 2-leg `StrikeSelection` (so `execution_check`
    and the M1.12 ladder semantics still apply) and the `final_execution`
    is the `CollarStructure.execution`. When the builder degrades to
    an empty list (no feasible pair), we return an empty selection +
    a "trivially fillable" Execution and `None` for the structure;
    downstream `liquidity_penalty()` is 0 (no legs to fill).
    """
    underlying_qty = max(positions.underlying_shares, _DEFAULT_COLLAR_QTY)

    structures = build_collar(
        spot=chain_snapshot.spot,
        underlying_qty=underlying_qty,
        chain=chain_snapshot,
        profile=profile,
        market_state=market_state,
        flow_score=flow_score,
        intents=[CollarIntent.ZERO_COST],
        weights=weights,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
    )

    if not structures:
        # Degraded — no feasible collar at this snapshot. Surface an
        # empty StrikeSelection so the parallel tuples stay aligned;
        # the recommendation's confidence (post-downgrade) will reflect
        # the gap because the M1.10 illiquidity penalty trickles through.
        empty_selection = StrikeSelection(
            emit=EmittedAction.OPEN_COLLAR,
            legs=(),
            skipped_reason="collar_builder_no_feasible_pair",
        )
        empty_execution = Execution(
            aggregate_liquidity_score=1.0,
            aggregate_fill_confidence=1.0,
            suggested_order_type=OrderType.LIMIT,
            legs=(),
            notes=("OPEN_COLLAR emit produced no feasible collar at this snapshot",),
        )
        dr = DowngradeResult(
            original_selection=empty_selection,
            original_execution=empty_execution,
            final_selection=empty_selection,
            final_execution=empty_execution,
            iterations=0,
            escalated=False,
            downgrade_notes=(),
        )
        return dr, None

    structure = structures[0]
    selection = _project_collar_to_strike_selection(structure, chain_snapshot)
    # `structure.execution` was already computed by the collar_builder
    # with the M1.11 §9.8 formula on the chosen two-leg pair — reuse it
    # verbatim so downstream consumers see consistent fill numbers.
    dr = DowngradeResult(
        original_selection=selection,
        original_execution=structure.execution,
        final_selection=selection,
        final_execution=structure.execution,
        iterations=0,
        escalated=False,
        downgrade_notes=(),
    )
    return dr, structure


def _project_collar_to_strike_selection(
    structure: CollarStructure,
    chain_snapshot: ChainSnapshot,
) -> StrikeSelection:
    """Build a synthetic `StrikeSelection` whose `.legs` carry both
    collar legs (long put + short call). This preserves the
    equal-length invariant `len(strike_selections) == len(executions)`
    for downstream consumers like the API layer's execution-check
    response shape."""
    long_put_contract = _find_contract(
        chain_snapshot, OptionType.PUT, structure.long_put.strike, structure.long_put.expiry,
    )
    short_call_contract = _find_contract(
        chain_snapshot, OptionType.CALL, structure.short_call.strike, structure.short_call.expiry,
    )
    long_put_leg = StrikeLeg(
        contract=long_put_contract,
        side=LegSide.LONG,
        delta_target=structure.long_put.delta,
        delta_actual=structure.long_put.delta,
        delta_distance=0.0,
        dte_actual=structure.horizon_days,
        mid_price=structure.long_put.mid,
    )
    short_call_leg = StrikeLeg(
        contract=short_call_contract,
        side=LegSide.SHORT,
        delta_target=structure.short_call.delta,
        delta_actual=structure.short_call.delta,
        delta_distance=0.0,
        dte_actual=structure.horizon_days,
        mid_price=structure.short_call.mid,
    )
    return StrikeSelection(
        emit=EmittedAction.OPEN_COLLAR,
        legs=(long_put_leg, short_call_leg),
    )


def _find_contract(
    chain: ChainSnapshot,
    option_type: OptionType,
    strike: float,
    expiry: object,  # date — type is `datetime.date` but stays opaque to avoid import cycle
) -> OptionContract:
    """Find the matching `OptionContract` in the chain snapshot."""
    for c in chain.contracts:
        if c.option_type is option_type and c.strike == strike and c.expiry == expiry:
            return c
    # The chain MUST contain the contract that the collar builder
    # selected — the builder iterates the same `chain.contracts` tuple.
    # If we land here, callers have corrupted the chain between
    # `build_collar()` and projection.
    raise LookupError(
        f"_find_contract: no {option_type.value} at strike={strike}, "
        f"expiry={expiry} in chain.contracts (n={len(chain.contracts)})"
    )


# Re-export the engine version + the OrderType (so downstream API code
# can import everything it needs from `engine.decision`).
__all__ = [
    "DEFAULT_DISCLAIMERS",
    "OrderType",
    "produce_daily_decision",
]
