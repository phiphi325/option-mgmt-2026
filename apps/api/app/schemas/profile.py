"""Request/response shapes for `GET/PUT /profile` (M1.17).

Per plan v1.2 §7 + §9.9 + §17 M1.17.

The profile is the user's `UserStrategyProfile` (per engine.profiles).
It is persisted to `users.strategy_profile` JSONB (column from M0.2 /
§22.6) and hydrated into the engine on every `/daily-plan` call.

## Why an API-layer wrapper schema

`engine.profiles.UserStrategyProfile` does NOT set `extra="forbid"` on
its model config — the engine's policy is to silently accept and drop
unknown fields, so a future engine can add new fields without breaking
forward-compat with older payloads (per ADR-0005 backwards-compat
discipline).

But the API boundary is the wrong place to be permissive: a typo in a
PUT body (`max_postion_pct` instead of `max_position_pct`) would
silently drop the user's intended update. Catching that as a 422 with
a clear error message is much better UX.

So `ProfileUpdateRequest` is a thin Pydantic subclass that re-declares
every field of `UserStrategyProfile` with `extra="forbid"`. Field
validation rules (range constraints, enum membership) inherit
automatically from the parent model's validators. The `to_engine()`
method serializes back to the engine type for service-layer use.

Per §9.9 validation rules — all enforced by `UserStrategyProfile`'s
Pydantic constraints; we don't re-implement them here.
"""

from __future__ import annotations

from engine.profiles import (
    IncomeNeed,
    ProfileStyle,
    RiskTolerance,
    UserStrategyProfile,
)
from pydantic import BaseModel, ConfigDict, Field

# `UserStrategyProfile` from the engine is the source of truth for response
# shape AND validation rules. GET returns it directly.
ProfileResponse = UserStrategyProfile


class ProfileUpdateRequest(BaseModel):
    """PUT /profile body — strict version that rejects unknown fields.

    Field types and validation rules are intentionally identical to
    `engine.profiles.UserStrategyProfile`. The only difference is
    `extra="forbid"` at the API boundary, so typos surface as 422
    rather than silently dropping fields.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    risk_tolerance: RiskTolerance
    income_need: IncomeNeed
    max_position_pct: float = Field(ge=0.0, le=1.0)
    max_coverage_pct: float = Field(ge=0.0, le=1.0)
    min_iv_rank_for_short_premium: int = Field(ge=0, le=100)
    prefer_collars_over_covered_calls: bool
    drawdown_tolerance: float = Field(ge=0.0, le=1.0)
    style: ProfileStyle

    def to_engine(self) -> UserStrategyProfile:
        """Project this API-layer input to the engine's frozen Pydantic model."""
        return UserStrategyProfile(
            risk_tolerance=self.risk_tolerance,
            income_need=self.income_need,
            max_position_pct=self.max_position_pct,
            max_coverage_pct=self.max_coverage_pct,
            min_iv_rank_for_short_premium=self.min_iv_rank_for_short_premium,
            prefer_collars_over_covered_calls=self.prefer_collars_over_covered_calls,
            drawdown_tolerance=self.drawdown_tolerance,
            style=self.style,
        )


__all__ = [
    "ProfileResponse",
    "ProfileUpdateRequest",
    "UserStrategyProfile",
]
