"""Engine endpoints — read/write surface on the M1.13 pipeline.

Per plan v1.2 §7 + §22.14 + §17 M1.14 + M1.15 + M1.16.

All endpoints require authentication (JWT-decoded user_id). The
business logic lives in `app.services.decision_service`; this module
is a thin HTTP-shape layer.

  POST /engine/daily-plan        → DailyDecisionResponse       (200 + persisted row)
  POST /engine/recommend         → RecommendResponse           (200; no persistence)
  POST /engine/what-if           → WhatIfResponse               (200; NEVER persists)
  POST /engine/market-state      → MarketStateResponse          (200; classify() only)
  POST /engine/flow-score        → FlowScoreResponse            (200; compute() only)
  POST /engine/strike-candidates → StrikeCandidatesResponse     (200; select_strikes() only)
  POST /engine/execution-check   → ExecutionCheckResponse       (200; assess() only)

Future endpoints in the same router:
  POST /engine/collar-builder    (M1.16a; deferred — requires M1.11a engine module
                                  `packages/engine/engine/collar_builder/` which
                                  is not yet shipped.)
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_authenticated_user_id, get_session
from app.schemas.decision import (
    DailyDecisionResponse,
    DailyPlanRequest,
    ExecutionCheckRequest,
    ExecutionCheckResponse,
    FlowScoreRequest,
    FlowScoreResponse,
    MarketStateRequest,
    MarketStateResponse,
    RecommendRequest,
    RecommendResponse,
    StrikeCandidatesRequest,
    StrikeCandidatesResponse,
    WhatIfRequest,
    WhatIfResponse,
)
from app.schemas.engine import decision_to_jsonable_dict
from app.services.decision_service import (
    produce_and_persist,
    run_execution_check,
    run_flow_score,
    run_market_state,
    run_recommend,
    run_strike_candidates,
    run_what_if,
)

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


# ----------------------------------------------------------------------
# M1.15 — read-only engine endpoints
# ----------------------------------------------------------------------


@router.post(
    "/what-if",
    response_model=WhatIfResponse,
    summary="Run the Master Decision Engine without persisting (what-if)",
)
async def what_if(
    request: WhatIfRequest,
    user_id: AuthedUserDep,
) -> WhatIfResponse:
    """V1 what-if endpoint per plan §17 M1.15 + §22.14.

    Runs `engine.produce_daily_decision()` against the request's
    hydrated inputs with optional flat overrides applied to
    `inputs.market_state` first. NEVER persists — caller can be
    confident no `daily_decisions` row is written regardless of the
    response's `inputs_hash`.

    Returns the full `DailyDecision` JSON projection plus an
    `is_new_row: Literal[False]` discriminant so client code that
    handles `DailyDecisionResponse` can also handle this shape.
    """
    # `user_id` is required for auth + future rate limiting; ack via _.
    _ = user_id

    try:
        decision = run_what_if(
            ticker=request.ticker,
            as_of=request.as_of,
            inputs=request.inputs,
            overrides=request.overrides,
        )
    except ValueError as exc:
        # Unknown override key — surface as 422 with the key list rather
        # than a 500 from a downstream model_copy ValidationError.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return WhatIfResponse(decision=decision_to_jsonable_dict(decision))


@router.post(
    "/market-state",
    response_model=MarketStateResponse,
    summary="Classify the market regime (no persistence)",
)
async def market_state(
    request: MarketStateRequest,
    user_id: AuthedUserDep,
) -> MarketStateResponse:
    """V1 market-state endpoint per plan §17 M1.15 + §9.2 + §22.3.

    Runs ONLY `engine.market_state.classify()`. No DB, no persistence.
    Returns the full `MarketStateResult` JSON projection.
    """
    _ = user_id  # auth required; rate-limit hook reserved.

    result = run_market_state(
        spot=request.spot,
        iv_rank=request.iv_rank,
        iv_percentile=request.iv_percentile,
        hv_30=request.hv_30,
        expected_move_pct=request.expected_move_pct,
        max_pain=request.max_pain,
        pcr_volume=request.pcr_volume,
        pcr_oi=request.pcr_oi,
        trend_strength=request.trend_strength,
        realized_vs_implied=request.realized_vs_implied,
        breakout_signal=request.breakout_signal,
        oi_concentration_at_max_pain=request.oi_concentration_at_max_pain,
        days_to_next_event=request.days_to_next_event,
        next_event_kind=request.next_event_kind,
        days_since_event=request.days_since_event,
        days_to_nearest_opex=request.days_to_nearest_opex,
        iv_rank_change_1d=request.iv_rank_change_1d,
        gap_pct=request.gap_pct,
    )
    return MarketStateResponse(market_state=decision_to_jsonable_dict(result))


@router.post(
    "/flow-score",
    response_model=FlowScoreResponse,
    summary="Compute the V1 Flow Score (no persistence)",
)
async def flow_score(
    request: FlowScoreRequest,
    user_id: AuthedUserDep,
) -> FlowScoreResponse:
    """V1 flow-score endpoint per plan §17 M1.15 + §9.3a.

    Runs ONLY `engine.flow_score.compute()`. No DB, no persistence.
    Returns the LOCKED V1 `FlowScore` contract (§22.2).
    """
    _ = user_id

    try:
        score = run_flow_score(
            chain_snapshot=request.chain_snapshot,
            spot=request.spot,
            expiry_focus=request.expiry_focus,
            dte_to_nearest_opex=request.dte_to_nearest_opex,
            risk_free_rate=request.risk_free_rate,
            dividend_yield=request.dividend_yield,
        )
    except ValueError as exc:
        # Engine raises ValueError on invalid inputs (e.g. no contracts
        # at any focus expiry). Surface as 422 with the engine's message.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return FlowScoreResponse(flow_score=decision_to_jsonable_dict(score))


# ----------------------------------------------------------------------
# M1.16 — strike + execution standalone endpoints
# ----------------------------------------------------------------------


@router.post(
    "/strike-candidates",
    response_model=StrikeCandidatesResponse,
    summary="Run the Strike Selector for one Action (no persistence)",
)
async def strike_candidates(
    request: StrikeCandidatesRequest,
    user_id: AuthedUserDep,
) -> StrikeCandidatesResponse:
    """V1 strike-candidates endpoint per plan §17 M1.16 + §9.4.

    Runs ONLY `engine.strike_selector.select_strikes()`. No DB, no
    persistence. Returns the `StrikeSelection` JSON projection (emit
    echo + 0..N legs + optional `skipped_reason`).
    """
    _ = user_id  # auth required; rate-limit hook reserved.

    try:
        selection = run_strike_candidates(
            action=request.action.to_engine(),
            chain_snapshot=request.chain_snapshot,
            risk_free_rate=request.risk_free_rate,
            dividend_yield=request.dividend_yield,
        )
    except ValueError as exc:
        # Engine raises ValueError on `chain_snapshot.spot <= 0` (defensive).
        # Other invalid inputs (empty chain, no eligible contracts) flow
        # through as `legs=()` + `skipped_reason` and produce 200.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return StrikeCandidatesResponse(
        strike_selection=decision_to_jsonable_dict(selection)
    )


@router.post(
    "/execution-check",
    response_model=ExecutionCheckResponse,
    summary="Run the Execution Feasibility Module for caller-supplied legs (no persistence)",
)
async def execution_check(
    request: ExecutionCheckRequest,
    user_id: AuthedUserDep,
) -> ExecutionCheckResponse:
    """V1 execution-check endpoint per plan §17 M1.16 + §9.8.

    Runs ONLY `engine.execution.assess()`. No DB, no persistence.
    Returns the `Execution` JSON projection (per-leg + aggregate
    feasibility scoring).

    Empty `legs` list is valid — the engine returns an aggregate-only
    `Execution` for REDUCE_COVERAGE / MONETIZE_PUT / NO_OP shapes.

    Length-mismatched `quantities` (when provided) surface as 422
    via the engine's `assess()` defensive check.
    """
    _ = user_id

    engine_legs = [leg.to_engine() for leg in request.legs]
    try:
        result = run_execution_check(
            legs=engine_legs,
            quantities=request.quantities,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return ExecutionCheckResponse(execution=decision_to_jsonable_dict(result))
