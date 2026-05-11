"""Recommendation Engine V1 contract types.

Per plan v1.2 §9.5 (Recommendation Engine) and §17 M1.8/M1.9.

M1.9 ships the plan-true contract with YAML-driven rules. Replaces the
simpler `Recommendation` / `StrategyClass` types shipped in the prior
M1.8 PR (#36) — see CHANGELOG `[1.0.0]` for the migration notes.

Pipeline (per plan §9.5):

  1. `REGIME_SPEC[regime].allowed_strategies` → whitelist.
  2. Score each rule from `rules_yaml` against the upstream state +
     position state + user profile.
  3. Top-scoring rule wins (first-match-wins in V1; the §9.5
     drawdown-impact tie-break lands in V1.5+).
  4. Generate `actions[]` by parameterizing the strategy template.
  5. Compute `coverage_after` based on emitted short-call contracts.

Frozen dataclasses per [ADR-0005](../decisions/0005-engine-pure-function-discipline.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from engine.regimes import Regime


class EmittedAction(StrEnum):
    """The eight V1 action codes per plan §22.8 `rules.yaml`.

    Each YAML rule emits exactly one of these. The mapping to a
    concrete `StrategyClass` + Strike Selector parameters is done by
    `recommend()` after rule evaluation.

    Wire-stable values — flow through to Postgres + TypeScript codegen.
    """

    SELL_COVERED_CALL_PARTIAL = "SELL_COVERED_CALL_PARTIAL"
    ROLL_UP_AND_OUT = "ROLL_UP_AND_OUT"
    REDUCE_COVERAGE = "REDUCE_COVERAGE"
    OPEN_COLLAR = "OPEN_COLLAR"
    BUY_LONG_DATED_PUT = "BUY_LONG_DATED_PUT"
    MONETIZE_PUT = "MONETIZE_PUT"
    WHEEL_SHORT_PUT = "WHEEL_SHORT_PUT"
    NO_OP = "NO_OP"


@dataclass(frozen=True)
class PositionState:
    """User's current option positions for the underlying.

    Used by the Recommendation Engine to evaluate position-dependent
    rule predicates: `has_short_call`, `has_short_call_within_pct`,
    `has_long_put`, `has_short_put`, `days_to_expiry_lte` (on the
    nearest short call), `put_pnl_pct_gte` (on the long put).

    The data layer hydrates this from the user's brokerage / position
    book before calling the engine — the engine itself has no I/O.

    All fields default to "no position" so a freshly-built profile can
    be used in tests without explicit position state.
    """

    underlying_shares: int = 0
    has_short_call: bool = False
    nearest_short_call_strike: float | None = None
    nearest_short_call_dte: int | None = None
    short_call_contracts: int = 0
    has_long_put: bool = False
    long_put_pnl_pct: float = 0.0
    has_short_put: bool = False


@dataclass(frozen=True)
class Action:
    """A single action emitted by the winning rule.

    Carries the action code + the forward-looking parameters the M1.7
    Strike Selector (and M1.13 Master Decision Engine) consume to
    pick concrete strikes. `parameters` keys are stable:

      target_dte:    target days to expiry for the new option leg
      target_delta:  target absolute delta of the new option leg
      size_pct:      fraction of position to act on
      urgency_days:  rough days-to-act window
    """

    emit: EmittedAction
    parameters: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class RuleSpec:
    """One YAML rule entry loaded from `rules.yaml`.

    Fields mirror the §22.8 YAML schema:

      id:           Stable identifier (snake_case).
      when:         The `when:` clause dict — opaque to the type;
                    interpreted by the rule evaluator.
      emit:         The `EmittedAction` enum value.
      rationale:    Templatable string ({{var}} placeholders).
      risks:        Tuple of risk caveats.
      invalidation: Tuple of conditions that invalidate the rule.

    Frozen for immutability + hashability.
    """

    id: str
    when: dict[str, Any]
    emit: EmittedAction
    rationale: str
    risks: tuple[str, ...] = ()
    invalidation: tuple[str, ...] = ()


@dataclass(frozen=True)
class MatchedRule:
    """A rule whose predicates fired, with the rendered rationale.

    `score` is the V1 binary 1.0 for any matching rule; V1.5+ will
    introduce continuous scoring per §9.5 step 3 (drawdown tie-break).
    """

    rule_id: str
    emit: EmittedAction
    score: float
    rationale: str
    risks: tuple[str, ...]
    invalidation: tuple[str, ...]


@dataclass(frozen=True)
class RecommendationResult:
    """V1 Recommendation Engine output per plan §9.5.

    Fields:
        actions:               Tuple of `Action`s emitted by the
                               winning rule. For most rules a single
                               action; `OPEN_COLLAR` may emit two
                               (short call + long put).
        matched_rule:          The winning `MatchedRule`. `None` when
                               no rule matched and the `hold_no_op`
                               fallback fired.
        regime:                Echoed `Regime` for traceability.
        coverage_after:        Estimated coverage ratio after the
                               emitted actions apply. In `[0, 1]`.
                               `0.0` when no underlying shares.
        confidence:            Echoed composite confidence from
                               upstream (V1 = `flow × regime`).
        rationale:             Per-action rationale strings rendered
                               from the matched rule's template.
        risks:                 Echoed risks from the matched rule.
        invalidation:          Echoed invalidation conditions.
        warnings:              Tuple of caveat strings (low confidence,
                               event proximity, etc.) — generated
                               independently of the rule pipeline.
        candidates_considered: Rule IDs that passed the regime
                               whitelist (i.e. rule.emit was in
                               `REGIME_SPEC[regime].allowed_strategies`).

    Frozen dataclass per ADR-0005.
    """

    actions: tuple[Action, ...]
    matched_rule: MatchedRule | None
    regime: Regime
    coverage_after: float
    confidence: float
    rationale: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    invalidation: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    candidates_considered: tuple[str, ...] = ()
