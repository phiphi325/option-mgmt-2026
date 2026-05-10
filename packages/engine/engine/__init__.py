"""MSFT Option Risk Management Engine — pure-function decision core.

Per ADR-0005, this package follows strict purity rules:
  - No DB, no network, no filesystem, no clock, no env reads.
  - Inputs flow in via typed args (frozen Pydantic models or dataclasses).
  - Outputs are typed return values; replays with identical inputs produce
    byte-equivalent results.

M0.6 ships only the type vocabulary. Scoring + decision functions land in M1+.
"""

from __future__ import annotations

from engine.profiles import IncomeNeed, RiskTolerance, UserStrategyProfile
from engine.regimes import REGIME_COLORS, Regime
from engine.types import ChainSnapshot, OptionContract, OptionType
from engine.version import __version__

__all__ = [
    "REGIME_COLORS",
    "ChainSnapshot",
    "IncomeNeed",
    "OptionContract",
    "OptionType",
    "Regime",
    "RiskTolerance",
    "UserStrategyProfile",
    "__version__",
]
