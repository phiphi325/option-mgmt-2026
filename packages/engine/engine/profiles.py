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


class ProfileStyle(StrEnum):
    """Overall portfolio style. Drives some §22.8 rule predicates
    (notably `wheel_on_low_iv_range` which requires `profile_style: "income"`).

    Distinct from `RiskTolerance` (which is about volatility tolerance):
    a `growth` portfolio can be either MODERATE or AGGRESSIVE risk, and an
    `income` portfolio is typically MODERATE risk with `IncomeNeed.HIGH`.

    Added in M1.9 (engine 1.0.0) for the plan v1.2 §22.8 rule vocabulary.
    """

    INCOME = "income"
    BALANCED = "balanced"
    GROWTH = "growth"


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

    # Drawdown tolerance — fraction of portfolio the user is willing to lose
    # in a worst-case scenario. Drives the §22.8 `drawdown_tolerance_lte`
    # predicate (e.g. rule `buy_long_dated_put_low_iv_trend` only fires when
    # `drawdown_tolerance <= 0.20`).
    #
    # Added in M1.9 (engine 1.0.0). Default 0.15 matches the plan §2 personas.
    drawdown_tolerance: float = Field(default=0.15, ge=0.0, le=1.0)

    # Overall portfolio style. Drives the §22.8 `profile_style` predicate
    # (e.g. rule `wheel_on_low_iv_range` only fires when style == "income").
    #
    # Added in M1.9. Default `BALANCED` is the safest fallback for callers
    # that haven't set a style yet.
    style: ProfileStyle = Field(default=ProfileStyle.BALANCED)
