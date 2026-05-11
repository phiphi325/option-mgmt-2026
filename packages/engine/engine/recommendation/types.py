"""Recommendation Engine result types.

Per plan v1.2 §9.4 (Recommendation Engine) and §17 M1.7.

`Recommendation` is the engine's output — a concrete strategy selection
plus the parameters the M1.8 Strike Selector and M1.11a Collar Builder
need to render an actionable trade.

The Recommendation Engine is the **decision layer** that sits between
the Flow Score Engine's `recommended_action` (a 6-value enum from
§9.3a) and the actual trade construction in M1.8 / M1.11a:

  Market State Engine ─┐
                       ├─► Recommendation Engine ─► Recommendation ─► Strike Selector / Collar Builder
  Flow Score Engine ───┤                                                  (M1.8 / M1.11a)
  User Profile ────────┘

The split exists because:

1. **Regime overrides flow.** A bullish FlowScore (action=SELL_CALL_AGGRESSIVE)
   in a HIGH_IV_PIN regime should NOT actually trigger aggressive call
   selling — the pin distorts the math. The Recommendation Engine applies
   this regime-aware whitelisting.
2. **User profile filters.** Conservative users see fewer aggressive
   strategies, even on the same engine signal. The Strike Selector
   doesn't have the profile context.
3. **Parameters belong downstream.** The Strike Selector needs
   target_dte / target_delta / size_pct — choices that depend on the
   recommendation, not the raw engine signal.

Phase 1.5 ADR-0008 plans to move the regime × action → strategy mapping
into an external `apps/api/app/config/rules.yaml` file so the rules can
be hot-swapped without engine version bumps. M1.7 ships the V1 rules as
in-engine constants and switch logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from engine.flow_score.types import RecommendedAction
from engine.regimes import Regime


class StrategyClass(StrEnum):
    """The concrete strategy the Recommendation Engine selects.

    Six values that map roughly to the §9.3a `RecommendedAction` enum
    but at a level the M1.8 Strike Selector and M1.11a Collar Builder
    can directly consume. The expansion vs the action enum:

      - `RecommendedAction.SELL_CALL_AGGRESSIVE` →
        `COVERED_CALL_AGGRESSIVE` (low-delta OTM call, larger size).
      - `RecommendedAction.SELL_CALL_PARTIAL` →
        `COVERED_CALL_PARTIAL` (closer-to-ATM call, smaller size).
      - `RecommendedAction.BUY_PROTECTION` →
        `PROTECTIVE_PUT` (lone OTM put) OR `COLLAR` (call+put combo)
        depending on `UserStrategyProfile.prefer_collars_over_covered_calls`.
      - `RecommendedAction.REDUCE_COVERAGE` →
        `REDUCE_CALL_COVERAGE` (close existing short calls).
      - `RecommendedAction.WAIT` → `WAIT`.
      - `RecommendedAction.MONITOR` → `MONITOR`.

    Regime overrides can downgrade any of these (e.g.
    `COVERED_CALL_AGGRESSIVE` → `COVERED_CALL_PARTIAL` in `HIGH_IV_EVENT`).

    The string values are wire-stable — they flow through to Postgres
    and the TypeScript UI types. Adding new values requires coordinated
    changes across all three layers.
    """

    COVERED_CALL_AGGRESSIVE = "COVERED_CALL_AGGRESSIVE"
    COVERED_CALL_PARTIAL = "COVERED_CALL_PARTIAL"
    PROTECTIVE_PUT = "PROTECTIVE_PUT"
    COLLAR = "COLLAR"
    REDUCE_CALL_COVERAGE = "REDUCE_CALL_COVERAGE"
    WAIT = "WAIT"
    MONITOR = "MONITOR"


@dataclass(frozen=True)
class Recommendation:
    """The Recommendation Engine output (V1 per §9.4).

    Fields:
        strategy_class:  Selected `StrategyClass` after regime + profile
                         overrides applied.
        action:          The original `RecommendedAction` from the
                         `FlowScore` (echoed for downstream traceability).
        regime:          The `Regime` from `MarketStateResult` (echoed
                         for traceability).
        confidence:      Composite confidence in `[0, 1]`. V1 formula:
                         `flow_score.confidence × regime_score`. The full
                         M1.10 Confidence Composer will replace this with
                         a richer multi-engine blend (per ADR-0003).
        rationale:       Human-readable 2-4 sentence summary.
        warnings:        Tuple of caveat strings. Empty when the
                         recommendation is uncomplicated.
        parameters:      Forward-looking parameters dict for downstream
                         consumers (Strike Selector, Collar Builder).
                         Stable keys: `target_dte`, `target_delta`,
                         `size_pct`, `urgency_days`. Values are floats.
                         Empty for `WAIT` / `MONITOR` strategies.

    All numeric fields are bounded as documented. Frozen dataclass per
    [ADR-0005](../decisions/0005-engine-pure-function-discipline.md);
    consumers MUST NOT mutate `warnings` or `parameters` (Python frozen
    dataclasses freeze attribute assignment, not deep-mutation of the
    contained collections — same convention as `FlowScore.breakdown`).
    """

    strategy_class: StrategyClass
    action: RecommendedAction
    regime: Regime
    confidence: float
    rationale: str
    warnings: tuple[str, ...] = field(default_factory=tuple)
    parameters: dict[str, float] = field(default_factory=dict)
