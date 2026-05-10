"""User strategy profile — the user-controllable inputs to the engine.

Per plan v1.2 §11 + ADR-0005, the engine receives a `UserStrategyProfile` as a
parameter (never `user_id`). The API layer hydrates it from the DB before
calling the engine; the engine itself has no I/O.

The model is frozen — once constructed, fields are immutable, which makes
hashing for `inputs_hash` straightforward (replay correctness depends on this).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class RiskTolerance(StrEnum):
    """How much downside variance the user is comfortable absorbing.

    Conservative → favor collars + protective puts; cap upside for downside floor.
    Moderate     → balanced; covered calls + occasional collars on event windows.
    Aggressive   → reduce coverage; allow ratio spreads, monetize puts on breakouts.
    """

    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class IncomeNeed(StrEnum):
    """Premium-income preference. Drives covered-call coverage % at fixed risk."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class UserStrategyProfile(BaseModel):
    """Frozen user profile — flows into the engine as a parameter (no I/O).

    All numeric thresholds are bounded so an out-of-range value produced by a
    buggy hydrator is caught at construction time, not silently propagated
    through scoring. Pydantic v2 enforces these via `Field(...)` constraints.

    Fields map to plan v1.2 §11 (User Strategy Profile) + §10 (Strike Selector
    inputs). Additional fields land as new engines arrive in M1+.
    """

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    risk_tolerance: RiskTolerance
    income_need: IncomeNeed

    # Position sizing (fraction of portfolio NAV).
    # 0.05 = 5% (conservative single-name cap), 1.0 = full portfolio (only on MSFT-only accounts).
    max_position_pct: float = Field(ge=0.0, le=1.0)

    # Coverage cap — fraction of long shares that may be written against (covered calls + collar shorts).
    # 0.0 disables income strategies entirely; 1.0 allows full coverage.
    max_coverage_pct: float = Field(ge=0.0, le=1.0)

    # Minimum IV rank (0..100) before the engine recommends short-premium strategies.
    # Below this threshold, the engine prefers protective puts / no action.
    min_iv_rank_for_short_premium: int = Field(ge=0, le=100)

    # When True, a collar is preferred over a naked covered call when both are
    # otherwise eligible (insurance bias). When False, plain covered calls are
    # preferred (income bias). Defaults are wired at the API layer, not here.
    prefer_collars_over_covered_calls: bool
