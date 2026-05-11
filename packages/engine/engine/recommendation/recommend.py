"""Recommendation Engine — V1 `recommend()` orchestrator (M1.9, plan-true).

Per plan v1.2 §9.5 (Recommendation Engine), §22.8 (eight V1 rules),
and §17 M1.9.

`recommend()` consumes the upstream Market State Engine + Flow Score
Engine + User Strategy Profile + the user's `PositionState`, and
applies YAML-driven rules to produce a `RecommendationResult`.

## Decision flow (per §9.5)

  1. `REGIME_SPEC[regime].allowed_strategies` → whitelist (handled
     inline by `engine.recommendation.rules.is_emit_in_regime_whitelist`).
  2. Iterate `rules` in YAML order. For each rule whose emit is in
     the whitelist, evaluate `RuleSpec.when` against the context.
     First match wins (V1; §9.5 step 3 drawdown tie-break is V1.5+).
  3. Render rationale template + emit `Action`(s) with downstream
     parameters.
  4. Compute `coverage_after` from emitted contracts vs underlying
     shares.

## V1 vs the plan signature

Plan §9.5 lists `chain_snapshot: ChainSnapshot` as an input. None of
the eight V1 rules actually read the chain — all position-related
clauses are answered by `PositionState`, all market-related clauses
by `MarketStateResult`. To keep `recommend()` pure under ADR-0005,
M1.9 drops `chain_snapshot` from the signature. A future rule that
needs chain-level liquidity / strike-grid context can re-add it.

Plan §9.5 also lists `rules_yaml: Path` as an input. Reading a YAML
file is I/O, which would violate ADR-0005. The M1.9 split: the
filesystem boundary lives in `engine.recommendation.yaml_loader`
(via `load_rules_yaml(path)` / `load_default_rules()`); `recommend()`
takes a `Sequence[RuleSpec]` (the parsed result). Callers can use
the loader once at startup and pass the parsed rules in.

## V1 ⇒ M1.8 mapping

The seven `StrategyClass` codes from the M1.8 PR (#36) are subsumed
by the eight `EmittedAction` codes. The mapping isn't 1-to-1 —
M1.9's emit codes are richer (e.g. `ROLL_UP_AND_OUT`, `MONETIZE_PUT`,
`WHEEL_SHORT_PUT` are new). The M1.8 PR's in-engine Python whitelist
is REPLACED by the YAML rule pipeline. Migration notes live in
CHANGELOG `[1.0.0]`.

Pure function per ADR-0005 — no I/O, no DB, no clock, no env.
"""

from __future__ import annotations

from collections.abc import Sequence

from engine._utils import clip01
from engine.flow_score.types import FlowScore
from engine.market_state.classify import MarketStateResult
from engine.profiles import UserStrategyProfile
from engine.recommendation.rationale import render_rationale
from engine.recommendation.rules import EvaluationContext, select_winning_rule
from engine.recommendation.types import (
    Action,
    EmittedAction,
    MatchedRule,
    PositionState,
    RecommendationResult,
    RuleSpec,
)
from engine.recommendation.warnings import build_warnings

# ----------------------------------------------------------------------
# Emit code → strategy template parameters (V1 priors per §9.5 step 4)
# ----------------------------------------------------------------------
#
# Each emit maps to forward-looking parameters for the M1.7 Strike
# Selector and (for COLLAR-style emits) the M1.11a Collar Builder.
# Stable keys: target_dte, target_delta, size_pct, urgency_days.
#
# Phase 4 ML may learn these from realized P&L per ADR-0008.

_PARAMETERS: dict[EmittedAction, dict[str, float]] = {
    EmittedAction.SELL_COVERED_CALL_PARTIAL: {
        "target_dte": 30.0,
        "target_delta": 0.35,
        "size_pct": 0.30,
        "urgency_days": 5.0,
    },
    EmittedAction.ROLL_UP_AND_OUT: {
        # Roll the existing short call: close at current strike +
        # open at higher strike, longer DTE.
        "target_dte": 45.0,
        "target_delta": 0.25,
        "size_pct": 1.00,  # full roll
        "urgency_days": 1.0,
    },
    EmittedAction.REDUCE_COVERAGE: {
        # Close half of existing short calls; no NEW leg.
        "target_dte": 0.0,
        "target_delta": 0.0,
        "size_pct": 0.50,
        "urgency_days": 1.0,
    },
    EmittedAction.OPEN_COLLAR: {
        "target_dte": 45.0,
        "target_delta": 0.25,
        "size_pct": 0.75,
        "urgency_days": 1.0,
    },
    EmittedAction.BUY_LONG_DATED_PUT: {
        "target_dte": 90.0,
        "target_delta": 0.20,
        "size_pct": 1.00,
        "urgency_days": 5.0,
    },
    EmittedAction.MONETIZE_PUT: {
        # Close the existing long put; no NEW leg.
        "target_dte": 0.0,
        "target_delta": 0.0,
        "size_pct": 1.00,
        "urgency_days": 1.0,
    },
    EmittedAction.WHEEL_SHORT_PUT: {
        "target_dte": 30.0,
        "target_delta": 0.30,
        "size_pct": 0.50,
        "urgency_days": 5.0,
    },
    EmittedAction.NO_OP: {},
}


# Emit codes that change coverage by adding a SHORT call leg.
# Used to compute `coverage_after`.
_INCREASES_COVERAGE: frozenset[EmittedAction] = frozenset(
    {EmittedAction.SELL_COVERED_CALL_PARTIAL, EmittedAction.OPEN_COLLAR}
)

# Emit codes that decrease coverage (close existing short calls).
_DECREASES_COVERAGE: frozenset[EmittedAction] = frozenset(
    {EmittedAction.REDUCE_COVERAGE, EmittedAction.MONETIZE_PUT}
)


# ----------------------------------------------------------------------
# Composite confidence (V1 two-engine multiplicative blend)
# ----------------------------------------------------------------------


def _composite_confidence(
    *,
    flow_score: FlowScore,
    market_state: MarketStateResult,
) -> float:
    """V1: `flow_score.confidence × market_state.regime_score`.

    M1.10 Confidence Composer will replace this with the multi-engine
    blend per ADR-0003.
    """
    return clip01(flow_score.confidence * market_state.regime_score)


# ----------------------------------------------------------------------
# Coverage calculation
# ----------------------------------------------------------------------


def _coverage_after(
    *,
    positions: PositionState,
    matched_rule: MatchedRule | None,
) -> float:
    """Estimate the post-action coverage ratio (short calls / 100 shares).

    Each short call covers 100 underlying shares. Per §9.5 step 5,
    coverage_after = (post-action short_call_contracts × 100) /
    underlying_shares.

    V1 calibration:
      - `SELL_COVERED_CALL_PARTIAL`: add `0.30 × (shares / 100)`
        contracts (matches `size_pct=0.30`).
      - `OPEN_COLLAR`: add `0.75 × (shares / 100)` short-call
        contracts (the collar's call leg).
      - `REDUCE_COVERAGE`: remove half of existing short calls.
      - `ROLL_UP_AND_OUT`: net zero change in count (close + open).
      - Other emits: no change in coverage.

    Returns `0.0` when the user has no underlying shares.
    """
    if positions.underlying_shares <= 0:
        return 0.0

    new_contracts = float(positions.short_call_contracts)

    if matched_rule is None:
        # NO_OP fallback wasn't even matched — no change.
        post = new_contracts
    elif matched_rule.emit is EmittedAction.SELL_COVERED_CALL_PARTIAL:
        new_contracts += 0.30 * (positions.underlying_shares / 100.0)
        post = new_contracts
    elif matched_rule.emit is EmittedAction.OPEN_COLLAR:
        new_contracts += 0.75 * (positions.underlying_shares / 100.0)
        post = new_contracts
    elif matched_rule.emit is EmittedAction.REDUCE_COVERAGE:
        new_contracts *= 0.5
        post = new_contracts
    elif matched_rule.emit is EmittedAction.ROLL_UP_AND_OUT:
        # net zero contract change
        post = new_contracts
    else:
        post = new_contracts

    coverage = (post * 100.0) / float(positions.underlying_shares)
    return clip01(coverage)


# ----------------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------------


def recommend(
    *,
    market_state: MarketStateResult,
    flow_score: FlowScore,
    positions: PositionState,
    profile: UserStrategyProfile,
    rules: Sequence[RuleSpec],
) -> RecommendationResult:
    """V1 Recommendation Engine `recommend()` per plan §9.5 (M1.9).

    Args:
        market_state: Upstream `MarketStateResult` from
            `engine.market_state.classify`.
        flow_score: Upstream `FlowScore` from `engine.flow_score.compute`.
        positions: User's current option position state for the
            underlying (`engine.recommendation.PositionState`). The
            data layer hydrates this; the engine has no I/O.
        profile: `UserStrategyProfile`. M1.9 expects the extended
            v1.0.0 profile with `drawdown_tolerance` + `style` fields.
        rules: Pre-parsed sequence of `RuleSpec`s. Typically the
            output of `engine.recommendation.yaml_loader.load_default_rules()`.

    Returns:
        `RecommendationResult` per plan §9.5. Carries `actions[]`,
        the `matched_rule`, `coverage_after`, plus rationale / risks /
        invalidation / warnings.

    Raises:
        ValueError: When `rules` is empty. (An empty rule set is
            almost certainly a configuration error — the no-op
            fallback lives in the YAML as `hold_no_op` and must be
            present.)

    Pure function (per ADR-0005). Same inputs → byte-identical output.
    """
    if not rules:
        raise ValueError(
            "recommend: `rules` is empty. The `hold_no_op` fallback rule "
            "must be present in the rule set."
        )

    confidence = _composite_confidence(
        flow_score=flow_score, market_state=market_state
    )

    ctx = EvaluationContext(
        market_state=market_state,
        flow_score=flow_score,
        positions=positions,
        profile=profile,
        confidence=confidence,
    )

    matched, candidates = select_winning_rule(rules=rules, ctx=ctx)

    # Build the actions tuple from the winning rule's emit.
    if matched is None:
        actions: tuple[Action, ...] = ()
        rationale: tuple[str, ...] = ()
        risks: tuple[str, ...] = ()
        invalidation: tuple[str, ...] = ()
    else:
        params = dict(_PARAMETERS.get(matched.emit, {}))
        actions = (Action(emit=matched.emit, parameters=params),)
        rendered = render_rationale(
            template=matched.rationale,
            market_state=market_state,
            flow_score=flow_score,
            positions=positions,
            profile=profile,
            confidence=confidence,
        )
        rationale = (rendered,)
        risks = matched.risks
        invalidation = matched.invalidation

    coverage = _coverage_after(positions=positions, matched_rule=matched)

    warnings = build_warnings(
        market_state=market_state,
        flow_score=flow_score,
        user_profile=profile,
    )

    return RecommendationResult(
        actions=actions,
        matched_rule=matched,
        regime=market_state.regime,
        coverage_after=coverage,
        confidence=confidence,
        rationale=rationale,
        risks=risks,
        invalidation=invalidation,
        warnings=warnings,
        candidates_considered=candidates,
    )
