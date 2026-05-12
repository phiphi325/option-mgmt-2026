"""Profile endpoints — `GET /profile` + `PUT /profile` (M1.17).

Per plan v1.2 §7 + §9.9 + §17 M1.17.

Both endpoints require authentication. The profile is the user's
`UserStrategyProfile` persisted to `users.strategy_profile` JSONB.

  GET /profile → 200 (always returns a profile; defaults when unset)
  PUT /profile → 200 (full replacement)
"""

from __future__ import annotations

from typing import Annotated

from engine.profiles import (
    IncomeNeed,
    ProfileStyle,
    RiskTolerance,
    UserStrategyProfile,
)
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_authenticated_user_id, get_session
from app.schemas.profile import ProfileResponse, ProfileUpdateRequest
from app.services.profile_service import get_profile, replace_profile

router = APIRouter(prefix="/profile", tags=["profile"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
AuthedUserDep = Annotated[str, Depends(get_authenticated_user_id)]


def _default_profile() -> UserStrategyProfile:
    """Sensible default profile for a fresh user. Sourced from §9.9 defaults
    — moderate risk, medium income need, 50% position cap, 75% coverage cap,
    40 IV-rank short-premium threshold, balanced style.
    """
    return UserStrategyProfile(
        risk_tolerance=RiskTolerance.MODERATE,
        income_need=IncomeNeed.MEDIUM,
        max_position_pct=0.50,
        max_coverage_pct=0.75,
        min_iv_rank_for_short_premium=40,
        prefer_collars_over_covered_calls=False,
        drawdown_tolerance=0.15,
        style=ProfileStyle.BALANCED,
    )


@router.get(
    "",
    response_model=ProfileResponse,
    summary="Get the authenticated user's strategy profile",
)
async def get_profile_endpoint(
    session: SessionDep,
    user_id: AuthedUserDep,
) -> ProfileResponse:
    """Returns the user's persisted UserStrategyProfile, or sensible
    defaults when the column is empty (new user)."""
    profile = await get_profile(session=session, user_id=user_id)
    if profile is None:
        profile = _default_profile()
    return profile


@router.put(
    "",
    response_model=ProfileResponse,
    summary="Replace the authenticated user's strategy profile",
)
async def put_profile_endpoint(
    request: ProfileUpdateRequest,
    session: SessionDep,
    user_id: AuthedUserDep,
) -> ProfileResponse:
    """Full replacement (PUT semantics, not PATCH).

    `ProfileUpdateRequest` enforces `extra="forbid"` at the API boundary
    — unknown fields raise 422 BEFORE the handler runs, so typos like
    `max_postion_pct` are caught loudly rather than silently dropped.
    Pydantic also enforces all §9.9 range constraints at the request
    boundary.

    `.to_engine()` projects to the engine's `UserStrategyProfile`
    (which has the same fields but `extra=ignore` for forward-compat
    with future engine additions).
    """
    try:
        engine_profile = request.to_engine()
        return await replace_profile(
            session=session, user_id=user_id, profile=engine_profile
        )
    except ValueError as exc:
        # user_id doesn't exist in `users` table — shouldn't happen for an
        # authenticated user but defensive code path.
        raise HTTPException(status_code=404, detail=str(exc)) from exc
