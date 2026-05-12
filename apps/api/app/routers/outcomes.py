"""Outcome endpoints — GET/POST list + create + PATCH (M1.17).

Per plan v1.2 §7 + §9.10 + §17 M1.17.

  GET    /outcomes?since=ISO&limit=N&cursor=…   → OutcomeListResponse
  POST   /outcomes                              → OutcomeResponse
  PATCH  /outcomes/{id}                         → OutcomeResponse

All endpoints require authentication. Ownership is enforced
transitively via the `daily_decisions.user_id` FK — cross-user access
returns 404 (we don't leak which decisions exist for other users).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_authenticated_user_id, get_session
from app.schemas.outcome import (
    OutcomeCreateRequest,
    OutcomeListResponse,
    OutcomePatchRequest,
    OutcomeResponse,
)
from app.services.outcome_service import (
    create_outcome,
    list_outcomes,
    update_outcome,
)

router = APIRouter(prefix="/outcomes", tags=["outcomes"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
AuthedUserDep = Annotated[str, Depends(get_authenticated_user_id)]


@router.get(
    "",
    response_model=OutcomeListResponse,
    summary="List outcomes for the authenticated user (cursor-paginated)",
)
async def list_outcomes_endpoint(
    session: SessionDep,
    user_id: AuthedUserDep,
    since: Annotated[datetime | None, Query(description="ISO datetime; filters out older outcomes")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query(description="Opaque cursor from a previous response's `next_cursor`")] = None,
) -> OutcomeListResponse:
    try:
        outcomes, next_cursor = await list_outcomes(
            session=session,
            user_id=user_id,
            since=since,
            limit=limit,
            cursor=cursor,
        )
    except ValueError as exc:
        # Invalid cursor format.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return OutcomeListResponse(outcomes=outcomes, next_cursor=next_cursor)


@router.post(
    "",
    response_model=OutcomeResponse,
    status_code=201,
    summary="Create an outcome tied to a daily_decision_id (manual entry)",
)
async def create_outcome_endpoint(
    request: OutcomeCreateRequest,
    session: SessionDep,
    user_id: AuthedUserDep,
) -> OutcomeResponse:
    try:
        return await create_outcome(
            session=session, user_id=user_id, request=request
        )
    except ValueError as exc:
        msg = str(exc)
        if "not_found" in msg:
            raise HTTPException(
                status_code=404,
                detail="daily_decision_id not found or not owned by user",
            ) from exc
        if "conflict" in msg:
            raise HTTPException(
                status_code=409,
                detail="outcome already exists for this daily_decision_id",
            ) from exc
        raise HTTPException(status_code=422, detail=msg) from exc


@router.patch(
    "/{outcome_id}",
    response_model=OutcomeResponse,
    summary="Update an outcome's fields (partial)",
)
async def patch_outcome_endpoint(
    outcome_id: UUID,
    request: OutcomePatchRequest,
    session: SessionDep,
    user_id: AuthedUserDep,
) -> OutcomeResponse:
    try:
        return await update_outcome(
            session=session,
            user_id=user_id,
            outcome_id=outcome_id,
            patch=request,
        )
    except ValueError as exc:
        if "not_found" in str(exc):
            raise HTTPException(
                status_code=404,
                detail="outcome not found or not owned by user",
            ) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc
