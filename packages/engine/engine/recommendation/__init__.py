"""Recommendation Engine — V1 `recommend()` orchestrator.

Per plan v1.2 §9.4 (Recommendation Engine) and §17 M1.7.

Consumes:
  - `engine.market_state.classify.MarketStateResult` (regime + tags)
  - `engine.flow_score.FlowScore` (action + bias + breakdown)
  - `engine.profiles.UserStrategyProfile` (risk tolerance, income need,
    IV-rank threshold, collar preference)

Produces:
  - `Recommendation` (frozen dataclass) — strategy class + action +
    regime + confidence + rationale + warnings + parameters.

Pure functions per ADR-0005 — no I/O, no DB, no clock, no env.
"""

from __future__ import annotations

from engine.recommendation.rationale import render_rationale
from engine.recommendation.recommend import recommend
from engine.recommendation.types import Recommendation, StrategyClass
from engine.recommendation.warnings import build_warnings

__all__ = [
    "Recommendation",
    "StrategyClass",
    "build_warnings",
    "recommend",
    "render_rationale",
]
