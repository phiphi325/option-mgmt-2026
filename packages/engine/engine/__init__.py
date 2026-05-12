"""MSFT Option Risk Management Engine — pure-function decision core.

Per ADR-0005, this package follows strict purity rules:
  - No DB, no network, no filesystem, no clock, no env reads.
  - Inputs flow in via typed args (frozen Pydantic models or dataclasses).
  - Outputs are typed return values; replays with identical inputs produce
    byte-equivalent results.

M0.6 ships only the type vocabulary. Scoring + decision functions land in M1+.
"""

from __future__ import annotations

from engine.collar_builder import (
    CollarIntent,
    CollarLeg,
    CollarStructure,
)
from engine.confidence import (
    DEFAULT_WEIGHTS,
    ConfidenceBreakdown,
    ConfidenceInputs,
    PenaltyCaps,
    PositiveWeights,
    Weights,
    compose,
    compute_confidence_inputs,
    load_default_weights,
    load_weights_yaml,
)
from engine.decision import (
    DEFAULT_DISCLAIMERS,
    DailyDecision,
    compute_inputs_hash,
    produce_daily_decision,
)
from engine.execution import (
    DOWNGRADE_THRESHOLD,
    DowngradeResult,
    Execution,
    ExecutionLeg,
    OrderType,
    assess,
    downgrade_if_needed,
    filter_chain_by_liquidity,
    liquidity_penalty,
)
from engine.flow_score import (
    Bias,
    FlowScore,
    RecommendedAction,
    compute,
    compute_dealer_gamma_proxy,
    compute_oi_walls,
)
from engine.greeks import (
    delta,
    gamma,
    rho,
    theta,
    time_to_expiry_years,
    vega,
)
from engine.market_state import MarketStateResult, classify
from engine.profiles import IncomeNeed, ProfileStyle, RiskTolerance, UserStrategyProfile
from engine.recommendation import (
    Action,
    EmittedAction,
    MatchedRule,
    PositionState,
    RecommendationResult,
    RuleSpec,
    load_default_rules,
    load_rules_yaml,
    recommend,
)
from engine.regimes import REGIME_COLORS, Regime
from engine.scoring import (
    EVENT_KIND_WEIGHTS,
    EventKind,
    EventScoreResult,
    EventStats,
    GammaScoreResult,
    GammaWall,
    IvScoreResult,
    OiWalls,
    StructureScoreResult,
    event_score,
    gamma_score,
    iv_score,
    structure_score,
)
from engine.strike_selector import (
    LegSide,
    StrikeLeg,
    StrikeSelection,
    select_strikes,
)
from engine.types import ChainSnapshot, OptionContract, OptionType
from engine.version import __version__

__all__ = [
    "DEFAULT_DISCLAIMERS",
    "DEFAULT_WEIGHTS",
    "DOWNGRADE_THRESHOLD",
    "DailyDecision",
    "DowngradeResult",
    "EVENT_KIND_WEIGHTS",
    "REGIME_COLORS",
    "Action",
    "Bias",
    "ChainSnapshot",
    "CollarIntent",
    "CollarLeg",
    "CollarStructure",
    "ConfidenceBreakdown",
    "ConfidenceInputs",
    "EmittedAction",
    "EventKind",
    "EventScoreResult",
    "EventStats",
    "Execution",
    "ExecutionLeg",
    "FlowScore",
    "GammaScoreResult",
    "GammaWall",
    "IncomeNeed",
    "IvScoreResult",
    "LegSide",
    "MarketStateResult",
    "MatchedRule",
    "OiWalls",
    "OptionContract",
    "OptionType",
    "OrderType",
    "PenaltyCaps",
    "PositionState",
    "PositiveWeights",
    "ProfileStyle",
    "RecommendationResult",
    "RecommendedAction",
    "Regime",
    "RiskTolerance",
    "RuleSpec",
    "StrikeLeg",
    "StrikeSelection",
    "StructureScoreResult",
    "UserStrategyProfile",
    "Weights",
    "__version__",
    "assess",
    "classify",
    "compose",
    "compute",
    "compute_confidence_inputs",
    "compute_dealer_gamma_proxy",
    "compute_inputs_hash",
    "compute_oi_walls",
    "delta",
    "downgrade_if_needed",
    "event_score",
    "filter_chain_by_liquidity",
    "gamma",
    "gamma_score",
    "iv_score",
    "liquidity_penalty",
    "load_default_rules",
    "load_default_weights",
    "load_rules_yaml",
    "load_weights_yaml",
    "produce_daily_decision",
    "recommend",
    "rho",
    "select_strikes",
    "structure_score",
    "theta",
    "time_to_expiry_years",
    "vega",
]
