"""Rule predicate evaluator for the Recommendation Engine.

Per plan v1.2 §9.5 (Recommendation Engine — rule pipeline) and §22.8
(eight V1 `rules.yaml` entries).

Each `RuleSpec.when` clause is a dict of predicate keys → expected
values. The evaluator iterates rule clauses and returns `True` only
when ALL clauses match. Clauses use a small vocabulary documented
inline.

V1 evaluation strategy:
  - Predicates AND together: every clause must match for the rule to
    fire (no `or` / `not` operators in V1; can be added in V1.5+).
  - Unknown clause keys raise `ValueError` early — better to fail
    loudly than silently miss a rule.
  - List-valued clauses (e.g. `regime: ["HIGH_IV_EVENT", "LOW_IV_RANGE"]`)
    treat the list as a set: any match passes.
  - Scalar `_gte` / `_lte` clauses compare numerically.
  - String clauses (`profile_style`) compare verbatim.

Pure functions per ADR-0005. Stdlib-only.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from engine.flow_score.types import FlowScore
from engine.market_state.classify import MarketStateResult
from engine.profiles import UserStrategyProfile
from engine.recommendation.types import (
    EmittedAction,
    MatchedRule,
    PositionState,
    RuleSpec,
)

# ----------------------------------------------------------------------
# Evaluation context
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class EvaluationContext:
    """All inputs visible to rule predicates.

    Bundled into one frozen dataclass so the evaluator's signature
    doesn't sprawl. Holds the four upstream engines' outputs + user
    profile + composite confidence.
    """

    market_state: MarketStateResult
    flow_score: FlowScore
    positions: PositionState
    profile: UserStrategyProfile
    confidence: float


# ----------------------------------------------------------------------
# Clause evaluators
# ----------------------------------------------------------------------
#
# Each clause key in the `when:` block maps to a small lambda over the
# `EvaluationContext`. The dispatch table below lists every supported
# key — adding a new clause means adding an entry here + a unit test.


def _eval_regime(value: Any, ctx: EvaluationContext) -> bool:
    """`regime: "REGIME"` or `regime: ["REGIME_A", "REGIME_B"]`."""
    regime_str = ctx.market_state.regime.value
    if isinstance(value, str):
        return regime_str == value
    if isinstance(value, list):
        return regime_str in value
    raise ValueError(f"regime clause: expected str or list, got {type(value).__name__}")


def _eval_iv_rank_gte(value: Any, ctx: EvaluationContext) -> bool:
    """`iv_rank_gte: 50` — IV rank ≥ value, on the 0-100 scale."""
    return ctx.market_state.iv_rank * 100.0 >= float(value)


def _eval_iv_rank_lte(value: Any, ctx: EvaluationContext) -> bool:
    return ctx.market_state.iv_rank * 100.0 <= float(value)


def _eval_iv_rank_change_1d_lte(value: Any, ctx: EvaluationContext) -> bool:
    """`iv_rank_change_1d_lte: -15` — 1-day IV-rank change ≤ value.

    The plan's threshold is in **percentage points** (e.g. `-15` means
    "IV rank dropped by 15 percentage points"). MarketStateResult does
    not currently carry an `iv_rank_change_1d` field at the dataclass
    level — when absent we conservatively return `False` (rule does
    not fire). This is the safe default per the engineering principle
    "missing data → skip, don't guess."
    """
    change: float | None = getattr(ctx.market_state, "iv_rank_change_1d", None)
    if change is None:
        return False
    return float(change) * 100.0 <= float(value)


def _eval_days_to_next_event_lte(value: Any, ctx: EvaluationContext) -> bool:
    d = ctx.market_state.days_to_next_event
    if d is None:
        return False
    return d <= int(value)


def _eval_days_since_event_lte(value: Any, ctx: EvaluationContext) -> bool:
    d = ctx.market_state.days_since_event
    if d is None:
        return False
    return d <= int(value)


def _eval_has_short_call(value: Any, ctx: EvaluationContext) -> bool:
    return ctx.positions.has_short_call == bool(value)


def _eval_has_short_call_within_pct(value: Any, ctx: EvaluationContext) -> bool:
    """`has_short_call_within_pct: 1.0` — short call strike within
    `value%` of current spot.
    """
    if not ctx.positions.has_short_call:
        return False
    strike = ctx.positions.nearest_short_call_strike
    if strike is None:
        return False
    spot = ctx.market_state.spot
    if spot <= 0.0:
        return False
    pct = abs(strike - spot) / spot * 100.0
    return pct <= float(value)


def _eval_has_long_put(value: Any, ctx: EvaluationContext) -> bool:
    return ctx.positions.has_long_put == bool(value)


def _eval_has_short_put(value: Any, ctx: EvaluationContext) -> bool:
    return ctx.positions.has_short_put == bool(value)


def _eval_days_to_expiry_lte(value: Any, ctx: EvaluationContext) -> bool:
    """Applies to the nearest short call's DTE (per §22.8 rule 2)."""
    dte = ctx.positions.nearest_short_call_dte
    if dte is None:
        return False
    return dte <= int(value)


def _eval_put_pnl_pct_gte(value: Any, ctx: EvaluationContext) -> bool:
    """`put_pnl_pct_gte: 0.30` — long put up at least `value` (fraction)."""
    if not ctx.positions.has_long_put:
        return False
    return ctx.positions.long_put_pnl_pct >= float(value)


def _eval_drawdown_tolerance_lte(value: Any, ctx: EvaluationContext) -> bool:
    """`drawdown_tolerance_lte: 0.20` — user's drawdown tolerance ≤ value.

    `UserStrategyProfile` carries `drawdown_tolerance` as a fraction
    in `[0, 1]`. When absent (older profile) we return `False` — the
    rule that depends on it should not fire silently.
    """
    tolerance: float | None = getattr(ctx.profile, "drawdown_tolerance", None)
    if tolerance is None:
        return False
    return float(tolerance) <= float(value)


def _eval_profile_style(value: Any, ctx: EvaluationContext) -> bool:
    """`profile_style: "income"` — user style matches verbatim.

    Compares against the enum's `.value` to be robust across Python
    StrEnum quirks (3.9 shim returns "ProfileStyle.INCOME" from
    `str()`; 3.12+ native returns "income").
    """
    style = getattr(ctx.profile, "style", None)
    if style is None:
        return False
    style_str = style.value if hasattr(style, "value") else str(style)
    return style_str == str(value)


def _eval_confidence_lte(value: Any, ctx: EvaluationContext) -> bool:
    """`confidence_lte: 0.30` — composite confidence ≤ value."""
    return ctx.confidence <= float(value)


# Dispatch table — keep sorted by key for grep-ability.
_CLAUSE_EVALUATORS: dict[str, Any] = {
    "confidence_lte": _eval_confidence_lte,
    "days_since_event_lte": _eval_days_since_event_lte,
    "days_to_expiry_lte": _eval_days_to_expiry_lte,
    "days_to_next_event_lte": _eval_days_to_next_event_lte,
    "drawdown_tolerance_lte": _eval_drawdown_tolerance_lte,
    "has_long_put": _eval_has_long_put,
    "has_short_call": _eval_has_short_call,
    "has_short_call_within_pct": _eval_has_short_call_within_pct,
    "has_short_put": _eval_has_short_put,
    "iv_rank_change_1d_lte": _eval_iv_rank_change_1d_lte,
    "iv_rank_gte": _eval_iv_rank_gte,
    "iv_rank_lte": _eval_iv_rank_lte,
    "profile_style": _eval_profile_style,
    "put_pnl_pct_gte": _eval_put_pnl_pct_gte,
    "regime": _eval_regime,
}


def supported_clauses() -> frozenset[str]:
    """Return the set of clause keys the V1 evaluator understands."""
    return frozenset(_CLAUSE_EVALUATORS.keys())


def evaluate_clause(*, key: str, value: Any, ctx: EvaluationContext) -> bool:
    """Evaluate a single clause against the context.

    Raises:
        ValueError: When `key` is not a supported clause.
    """
    evaluator = _CLAUSE_EVALUATORS.get(key)
    if evaluator is None:
        raise ValueError(
            f"Unknown rule clause '{key}'. Supported clauses: "
            f"{sorted(_CLAUSE_EVALUATORS)}"
        )
    return bool(evaluator(value, ctx))


def matches(rule: RuleSpec, ctx: EvaluationContext) -> bool:
    """Return True iff every clause in `rule.when` matches the context."""
    for key, value in rule.when.items():
        if not evaluate_clause(key=key, value=value, ctx=ctx):
            return False
    return True


# ----------------------------------------------------------------------
# Regime whitelist (per §9.1 REGIME_SPEC.allowed_strategies)
# ----------------------------------------------------------------------
#
# Maps `EmittedAction` codes to the regime-strategy whitelist. Per
# §9.5 step 1, a rule is only considered if its emit code is in the
# current regime's allowed_strategies. The mapping below mirrors the
# §9.1 REGIME_SPEC (which uses different string codes — "OPEN_COLLAR"
# matches both `OPEN_COLLAR` and `RE_STRIKE_COLLAR` etc.).
#
# V1 mapping is a strict subset — only the codes the 8 V1 rules
# actually emit. The plan's full REGIME_SPEC has more codes that
# future rules can add.


def is_emit_in_regime_whitelist(emit: EmittedAction, regime: Any) -> bool:
    """V1 regime whitelist for the 8 rules.

    Per plan §9.1 `REGIME_SPEC[regime].allowed_strategies`:

      HIGH_IV_EVENT       → OPEN_COLLAR, SELL_COVERED_CALL_PARTIAL
      HIGH_IV_PIN         → SELL_COVERED_CALL_PARTIAL (subset)
      LOW_IV_TREND        → BUY_LONG_DATED_PUT, REDUCE_COVERAGE
      LOW_IV_RANGE        → SELL_COVERED_CALL_PARTIAL, WHEEL_SHORT_PUT,
                            ROLL_UP_AND_OUT (M1.24: short-call roll valid in any regime)
      BREAKOUT            → ROLL_UP_AND_OUT, REDUCE_COVERAGE, MONETIZE_PUT
      POST_EVENT_REPRICE  → SELL_COVERED_CALL_PARTIAL, OPEN_COLLAR
                            (M1.24: collar reprice is a valid post-event action)

    NO_OP is always allowed (fallback).
    """
    if emit is EmittedAction.NO_OP:
        return True

    regime_name = regime.value if hasattr(regime, "value") else str(regime)

    whitelist: dict[str, frozenset[EmittedAction]] = {
        "HIGH_IV_EVENT": frozenset(
            {EmittedAction.OPEN_COLLAR, EmittedAction.SELL_COVERED_CALL_PARTIAL}
        ),
        "HIGH_IV_PIN": frozenset({EmittedAction.SELL_COVERED_CALL_PARTIAL}),
        "LOW_IV_TREND": frozenset(
            {EmittedAction.BUY_LONG_DATED_PUT, EmittedAction.REDUCE_COVERAGE}
        ),
        "LOW_IV_RANGE": frozenset(
            {
                EmittedAction.SELL_COVERED_CALL_PARTIAL,
                EmittedAction.WHEEL_SHORT_PUT,
                EmittedAction.ROLL_UP_AND_OUT,
            }
        ),
        "BREAKOUT": frozenset(
            {
                EmittedAction.ROLL_UP_AND_OUT,
                EmittedAction.REDUCE_COVERAGE,
                EmittedAction.MONETIZE_PUT,
            }
        ),
        "POST_EVENT_REPRICE": frozenset(
            {EmittedAction.SELL_COVERED_CALL_PARTIAL, EmittedAction.OPEN_COLLAR}
        ),
    }
    return emit in whitelist.get(regime_name, frozenset())


# ----------------------------------------------------------------------
# Top-level rule selection
# ----------------------------------------------------------------------


def select_winning_rule(
    *,
    rules: Sequence[RuleSpec],
    ctx: EvaluationContext,
) -> tuple[MatchedRule | None, tuple[str, ...]]:
    """Iterate `rules`; return the first matching rule + diagnostics.

    Per plan §9.5 step 3, "Top-scoring strategy wins. If two within
    0.05, pick the one with lower drawdown impact." V1 implements
    this as first-match-wins by YAML order, since the 8 V1 rules have
    binary scores and no two are designed to fire simultaneously
    (the regime whitelist + `when:` predicates partition the regime
    × position space).

    Returns:
        (matched_rule_or_None, candidates_considered):
            - matched_rule: the winning `MatchedRule` or `None` if no
              rule matched the regime whitelist + predicates.
            - candidates_considered: tuple of rule IDs that passed
              the regime whitelist (i.e. were evaluated).
    """
    candidates: list[str] = []
    for rule in rules:
        if not is_emit_in_regime_whitelist(rule.emit, ctx.market_state.regime):
            continue
        candidates.append(rule.id)
        if matches(rule, ctx):
            return (
                MatchedRule(
                    rule_id=rule.id,
                    emit=rule.emit,
                    score=1.0,
                    rationale=rule.rationale,
                    risks=rule.risks,
                    invalidation=rule.invalidation,
                ),
                tuple(candidates),
            )
    return None, tuple(candidates)
