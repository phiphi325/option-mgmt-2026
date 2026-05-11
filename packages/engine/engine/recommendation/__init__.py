"""Recommendation Engine — V1 `recommend()` orchestrator (M1.9).

Per plan v1.2 §9.5 (Recommendation Engine — YAML-driven rules),
§22.8 (eight V1 rule definitions), §17 M1.8 + M1.9.

Consumes:
  - `engine.market_state.classify.MarketStateResult` (regime + tags +
    echoed inputs)
  - `engine.flow_score.FlowScore` (action + bias + confidence)
  - `engine.recommendation.PositionState` (user's current option
    positions for the underlying)
  - `engine.profiles.UserStrategyProfile` (risk tolerance, income
    need, drawdown tolerance, style, IV-rank threshold, collar
    preference)
  - A `Sequence[RuleSpec]` (pre-parsed rules) — typically loaded via
    `load_default_rules()` from the packaged `config/rules.yaml`.

Produces:
  - `RecommendationResult` (frozen dataclass) — `actions[]`,
    `matched_rule`, `coverage_after`, `confidence`, rationale, risks,
    invalidation, warnings.

Pure functions per ADR-0005 — no I/O, no DB, no clock, no env.
The single filesystem boundary is `yaml_loader.load_rules_yaml()` /
`load_default_rules()`; the orchestrator `recommend()` is fully pure.
"""

from __future__ import annotations

from engine.recommendation.rationale import render_rationale
from engine.recommendation.recommend import recommend
from engine.recommendation.rules import (
    EvaluationContext,
    evaluate_clause,
    is_emit_in_regime_whitelist,
    matches,
    select_winning_rule,
    supported_clauses,
)
from engine.recommendation.types import (
    Action,
    EmittedAction,
    MatchedRule,
    PositionState,
    RecommendationResult,
    RuleSpec,
)
from engine.recommendation.warnings import build_warnings
from engine.recommendation.yaml_loader import load_default_rules, load_rules_yaml

__all__ = [
    "Action",
    "EmittedAction",
    "EvaluationContext",
    "MatchedRule",
    "PositionState",
    "RecommendationResult",
    "RuleSpec",
    "build_warnings",
    "evaluate_clause",
    "is_emit_in_regime_whitelist",
    "load_default_rules",
    "load_rules_yaml",
    "matches",
    "recommend",
    "render_rationale",
    "select_winning_rule",
    "supported_clauses",
]
