"""Decision service — wires M1.13 `produce_daily_decision()` into the API.

Per plan v1.2 §7 (idempotency notes) and §17 M1.14.

The engine is pure-function per ADR-0005; this service layer owns the
I/O: it hydrates inputs from request bodies (V1) or Postgres rows
(M1.15+), calls the engine, and persists results.

Persistence semantics (`produce_and_persist`):

  - Compute `DailyDecision` via `engine.produce_daily_decision()`.
  - Insert a `daily_decisions` row with the full JSON payload + the
    three pin columns (`engine_version`, `weights_version`, `inputs_hash`).
  - Idempotency: `INSERT ... ON CONFLICT (user_id, inputs_hash) DO NOTHING
    RETURNING id`. Concurrent calls with the same hash collapse to the
    same row; the returned `is_new_row` flag tells the caller whether
    the insert actually wrote a new row (True) or hit an existing one
    (False).

The `UNIQUE (user_id, inputs_hash)` constraint is added by migration
`0002_daily_decisions_unique_inputs_hash.py`.

Pure-function engine call + thin DB wrapper. No additional engine logic
lives here — that all belongs in `packages/engine/`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from engine import (
    DailyDecision,
    RecommendationResult,
    produce_daily_decision,
    recommend,
)
from engine.recommendation.yaml_loader import load_default_rules
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.decision import EngineInputs
from app.schemas.engine import decision_to_jsonable_dict


async def produce_and_persist(
    *,
    session: AsyncSession,
    user_id: str,
    ticker: str,
    as_of: datetime | None,
    inputs: EngineInputs,
    persist: bool = True,
) -> tuple[DailyDecision, bool]:
    """Run the Master Decision Engine and (optionally) persist the result.

    Args:
        session:   Async SQLAlchemy session (from `app.deps.get_session`).
        user_id:   Authenticated user UUID (string).
        ticker:    Underlying symbol (MSFT-only in V1; reserved for multi-ticker).
        as_of:     Decision-time timestamp. Defaults to `datetime.now(UTC)` when None.
        inputs:    Full hydrated input bundle (M1.14 V1 — eventually replaced
                   by DB hydration once M1.15+ data endpoints ship).
        persist:   When True, INSERT a `daily_decisions` row with idempotency
                   via ON CONFLICT (user_id, inputs_hash) DO NOTHING.

    Returns:
        `(decision, is_new_row)` — the engine output plus a flag indicating
        whether persistence actually wrote a new row. `is_new_row=False`
        when an existing row with the same `(user_id, inputs_hash)` was
        already present (idempotent retry hit).

    Raises:
        ValueError: When the engine rejects the inputs (e.g. empty rules).
    """
    effective_as_of = as_of if as_of is not None else datetime.now(timezone.utc)  # noqa: UP017

    decision: DailyDecision = produce_daily_decision(
        as_of=effective_as_of,
        ticker=ticker,
        chain_snapshot=inputs.chain_snapshot,
        positions=inputs.positions.to_engine(),
        profile=inputs.profile,
        market_state=inputs.market_state.to_engine(),
        flow_score=inputs.flow_score.to_engine(),
    )

    is_new_row = False
    if persist:
        is_new_row = await _persist_decision(
            session=session,
            user_id=user_id,
            decision=decision,
        )

    return decision, is_new_row


async def run_recommend(
    *,
    ticker: str,
    market_state: Any,
    flow_score: Any,
    positions: Any,
    profile: Any,
) -> RecommendationResult:
    """Run the M1.9 Recommendation Engine ONLY.

    No strike selection, no execution feasibility, no two-stage composer,
    no persistence. Use for UI drill-down or rule-matching debugging.

    Args:
        ticker:        Echoed; not yet used by the V1 rule pipeline.
        market_state:  Engine `MarketStateResult` (already projected via
                       `MarketStateResultModel.to_engine()`).
        flow_score:    Engine `FlowScore`.
        positions:     Engine `PositionState`.
        profile:       Engine `UserStrategyProfile`.

    Returns:
        `RecommendationResult` with matched rule + actions + rationale +
        the M1.10 confidence breakdown (computed with `illiquidity_penalty=0`
        since no execution feasibility runs here).
    """
    # `ticker` is included in the public signature for symmetry with the
    # request shape but the V1 rule pipeline is ticker-agnostic.
    _ = ticker

    rules = load_default_rules()
    result: RecommendationResult = recommend(
        market_state=market_state,
        flow_score=flow_score,
        positions=positions,
        profile=profile,
        rules=rules,
        # M1.14 V1: `/engine/recommend` returns the pre-execution view.
        # The /engine/daily-plan endpoint runs the full two-stage pipeline.
        illiquidity_penalty=0.0,
    )
    return result


# ----------------------------------------------------------------------
# Internals
# ----------------------------------------------------------------------


_PERSIST_SQL = text(
    """
    INSERT INTO daily_decisions (
        user_id, ticker, as_of, payload, confidence,
        confidence_breakdown, execution,
        weights_version, engine_version, inputs_hash
    )
    VALUES (
        :user_id, :ticker, :as_of, CAST(:payload AS jsonb), :confidence,
        CAST(:confidence_breakdown AS jsonb), CAST(:execution AS jsonb),
        :weights_version, :engine_version, :inputs_hash
    )
    ON CONFLICT (user_id, inputs_hash) DO NOTHING
    RETURNING id;
    """
)


async def _persist_decision(
    *,
    session: AsyncSession,
    user_id: str,
    decision: DailyDecision,
) -> bool:
    """Insert a `daily_decisions` row with idempotency.

    Returns True when a new row was inserted; False when ON CONFLICT
    fired (meaning a row with the same `(user_id, inputs_hash)` already
    exists from a prior call).
    """
    import json

    payload_dict = decision_to_jsonable_dict(decision)
    breakdown_dict = (
        decision_to_jsonable_dict(decision.confidence_breakdown)
        if decision.confidence_breakdown is not None
        else {}
    )
    # The `execution` JSONB column captures the per-action executions
    # tuple (M1.13 holds them alongside DowngradeResult).
    execution_list = [
        decision_to_jsonable_dict(ex) for ex in decision.executions
    ]

    result = await session.execute(
        _PERSIST_SQL,
        {
            "user_id": user_id,
            "ticker": decision.ticker,
            "as_of": decision.as_of,
            "payload": json.dumps(payload_dict),
            "confidence": decision.confidence,
            "confidence_breakdown": json.dumps(breakdown_dict),
            "execution": json.dumps(execution_list),
            "weights_version": decision.weights_version,
            "engine_version": decision.engine_version,
            "inputs_hash": decision.inputs_hash,
        },
    )
    inserted_id = result.scalar()
    await session.commit()
    return inserted_id is not None
