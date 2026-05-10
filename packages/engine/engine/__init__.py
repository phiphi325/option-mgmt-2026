"""MSFT Option Risk Management Engine — pure-function decision core.

Per ADR-0005, this package follows strict purity rules:
  - No DB, no network, no filesystem, no clock, no env reads.
  - Inputs flow in via typed args (frozen Pydantic models or dataclasses).
  - Outputs are typed return values; replays with identical inputs produce
    byte-equivalent results.

M0.6 ships only the type vocabulary. Scoring + decision functions land in M1+.
"""

from __future__ import annotations

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
from engine.profiles import IncomeNeed, RiskTolerance, UserStrategyProfile
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
from engine.types import ChainSnapshot, OptionContract, OptionType
from engine.version import __version__

__all__ = [
    "EVENT_KIND_WEIGHTS",
    "REGIME_COLORS",
    "Bias",
    "ChainSnapshot",
    "EventKind",
    "EventScoreResult",
    "EventStats",
    "FlowScore",
    "GammaScoreResult",
    "GammaWall",
    "IncomeNeed",
    "IvScoreResult",
    "MarketStateResult",
    "OiWalls",
    "OptionContract",
    "OptionType",
    "RecommendedAction",
    "Regime",
    "RiskTolerance",
    "StructureScoreResult",
    "UserStrategyProfile",
    "__version__",
    "classify",
    "compute",
    "compute_dealer_gamma_proxy",
    "compute_oi_walls",
    "delta",
    "event_score",
    "gamma",
    "gamma_score",
    "iv_score",
    "rho",
    "structure_score",
    "theta",
    "time_to_expiry_years",
    "vega",
]
