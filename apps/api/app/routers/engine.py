"""Engine endpoints — `POST /engine/daily-plan`, `POST /engine/recommend`.

Per plan v1.2 §7 + §17 M1.14.

Both endpoints require authentication (JWT-decoded user_id). The
business logic lives in `app.services.decision_service`; this module
is a thin HTTP-shape layer.

  POST /engine/daily-plan  → DailyDecisionResponse  (200 + persisted row)
  POST /engine/recommend   → RecommendResponse      (200; no persistence)

Future endpoints in the same router (M1.15+):
  POST /engine/what-if         (M1.15; non-persisting variant of daily-plan)
  POST /engine/market-state    (M1.15; standalone classify())
  POST /engine/flow-score      (M1.15; standalone compute())
  POST /engine/strike-candidates (M1.16; standalone select_strikes())
  POST /engine/execution-check (M1.16; standalone assess())
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_authenticated_user_id, get_session
from app.schemas.decision import (
    DailyDecisionResponse,
    DailyPlanRequest,
    RecommendRequest,
    RecommendResponse,
)
from app.schemas.engine import decision_to_jsonable_dict
from app.services.decision_service import produce_and_persist, run_recommend

router = APIRouter(prefix="/engine", tags=["engine"])

# Annotated dependency aliases — modern FastAPI idiom (>=0.95). Avoids
# B008 (Depends in argument defaults) per docs/engineering-principles.md.
SessionDep = Annotated[AsyncSession, Depends(get_session)]
AuthedUserDep = Annotated[str, Depends(get_authenticated_user_id)]


@router.post(
    "/daily-plan",
    response_model=DailyDecisionResponse,
    summary="Run the Master Decision Engine and persist a DailyDecision",
)
async def daily_plan(
    request: DailyPlanRequest,
    session: SessionDep,
    user_id: AuthedUserDep,
) -> DailyDecisionResponse:
    """V1 daily-plan endpoint per plan §17 M1.14.

    Runs `engine.produce_daily_decision()` against the request's
    hydrated inputs (V1 — M1.15+ optionally hydrates from Postgres
    when `inputs` is omitted). Persists a `daily_decisions` row when
    `persist=True` (default); idempotency via `ON CONFLICT (user_id,
    inputs_hash) DO NOTHING`.

    Returns the full `DailyDecision` JSON projection plus an
    `is_new_row` flag distinguishing fresh inserts from idempotent hits.
    """
    decision, is_new_row = await produce_and_persist(
        session=session,
        user_id=user_id,
        ticker=request.ticker,
        as_of=request.as_of,
        inputs=request.inputs,
        persist=request.persist,
    )
    return DailyDecisionResponse(
        decision=decision_to_jsonable_dict(decision),
        is_new_row=is_new_row,
    )


@router.post(
    "/recommend",
    response_model=RecommendResponse,
    summary="Run the M1.9 Recommendation Engine only (no persistence)",
)
async def recommend_endpoint(
    request: RecommendRequest,
    user_id: AuthedUserDep,
) -> RecommendResponse:
    """V1 recommend endpoint per plan §17 M1.14.

    Runs ONLY the M1.9 rule pipeline (no strike selection, no
    execution feasibility, no persistence). Returns the
    `RecommendationResult` JSON projection.

    The user is authenticated (per ADR-0001 + §15) so request rate
    limiting can scope to user_id when added.
    """
    # `user_id` is required for auth + future rate limiting; ack via _.
    _ = user_id

    rec = await run_recommend(
        ticker=request.ticker,
        market_state=request.market_state.to_engine(),
        flow_score=request.flow_score.to_engine(),
        positions=request.positions.to_engine(),
        profile=request.profile,
    )
    return RecommendResponse(recommendation=decision_to_jsonable_dict(rec))
