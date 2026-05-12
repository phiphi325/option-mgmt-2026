"""Decision service — wires the engine modules into the API.

Per plan v1.2 §7 (idempotency notes), §22.14 (what-if non-persistence),
and §17 M1.14 + M1.15.

The engine is pure-function per ADR-0005; this service layer owns the
I/O: it hydrates inputs from request bodies (V1) or Postgres rows
(M1.17+), calls the engine, and (where applicable) persists results.

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
`0002_dd_unique_user_hash.py`.

M1.15 service functions (`run_what_if`, `run_market_state`, `run_flow_score`)
are pure read-only wrappers around the matching engine entry points.
What-if explicitly NEVER persists (§22.14); the other two have nothing
to persist (no `daily_decisions` row maps to a sub-step output in V1).

Pure-function engine call + thin DB wrapper. No additional engine logic
lives here — that all belongs in `packages/engine/`.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timezone
from typing import Any

from engine import (
    DailyDecision,
    RecommendationResult,
    produce_daily_decision,
    recommend,
)
from engine.execution import Execution, assess
from engine.flow_score import compute as flow_score_compute
from engine.flow_score.types import FlowScore
from engine.market_state.classify import MarketStateResult, classify
from engine.recommendation import Action
from engine.recommendation.yaml_loader import load_default_rules
from engine.strike_selector import StrikeLeg, StrikeSelection, select_strikes
from engine.types import ChainSnapshot
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.decision import EngineInputs
from app.schemas.engine import MarketStateResultModel, decision_to_jsonable_dict


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


# ----------------------------------------------------------------------
# M1.15 — read-only engine wrappers (no persistence)
# ----------------------------------------------------------------------


def _apply_market_state_overrides(
    inputs: EngineInputs,
    overrides: dict[str, Any],
) -> EngineInputs:
    """Apply flat overrides to `inputs.market_state` for what-if requests.

    Per plan §22.14 + the M1.15 dev spec, the `WhatIfRequest.overrides`
    dict maps `MarketStateResultModel` field names to override values.
    Examples: `{"spot": 425.0, "iv_rank": 0.35}`.

    Validates keys against `MarketStateResultModel.model_fields` so
    unknown overrides surface as a clear 422 message rather than a
    downstream Pydantic ValidationError on `model_copy`.

    Validates VALUES by re-validating the patched model via the full
    `MarketStateResultModel(**merged)` constructor (rather than
    `model_copy(update=...)` which can skip per-field validation
    depending on Pydantic version). This guarantees overrides like
    `{"iv_rank": 1.5}` raise here, not deep inside the engine.

    Raises:
        ValueError: One or more override keys are unknown OR the
            patched model violates field constraints. The router
            maps this into HTTP 422.
    """
    if not overrides:
        return inputs

    allowed = set(MarketStateResultModel.model_fields.keys())
    unknown = sorted(k for k in overrides if k not in allowed)
    if unknown:
        raise ValueError(
            f"unsupported override keys (must match MarketStateResultModel fields): {unknown}"
        )

    merged = {**inputs.market_state.model_dump(), **overrides}
    try:
        new_market_state = MarketStateResultModel(**merged)
    except Exception as exc:
        raise ValueError(f"override produced invalid market_state: {exc}") from exc

    return inputs.model_copy(update={"market_state": new_market_state})


def run_what_if(
    *,
    ticker: str,
    as_of: datetime | None,
    inputs: EngineInputs,
    overrides: dict[str, Any],
) -> DailyDecision:
    """Run the Master Decision Engine for a what-if scenario.

    Per plan §22.14: what-if explicitly NEVER persists. The caller is
    responsible for re-using or discarding the result — no DB row is
    written regardless of the response's `inputs_hash`.

    Args:
        ticker:    Underlying symbol.
        as_of:     Decision-time. Defaults to `datetime.now(UTC)` when None.
        inputs:    Full hydrated input bundle (V1 — same shape as
                   DailyPlanRequest.inputs).
        overrides: Flat `market_state.*` field overrides applied before
                   the engine runs. See `_apply_market_state_overrides`.

    Returns:
        The full `DailyDecision`. NO persistence side-effect.

    Raises:
        ValueError: Unknown override key (router maps to 422).
    """
    effective_as_of = as_of if as_of is not None else datetime.now(timezone.utc)  # noqa: UP017
    effective_inputs = _apply_market_state_overrides(inputs, overrides)

    return produce_daily_decision(
        as_of=effective_as_of,
        ticker=ticker,
        chain_snapshot=effective_inputs.chain_snapshot,
        positions=effective_inputs.positions.to_engine(),
        profile=effective_inputs.profile,
        market_state=effective_inputs.market_state.to_engine(),
        flow_score=effective_inputs.flow_score.to_engine(),
    )


def run_market_state(
    *,
    spot: float,
    iv_rank: float,
    iv_percentile: float,
    hv_30: float,
    expected_move_pct: float,
    max_pain: float,
    pcr_volume: float,
    pcr_oi: float,
    trend_strength: float,
    realized_vs_implied: float,
    breakout_signal: float,
    oi_concentration_at_max_pain: float,
    days_to_next_event: int | None,
    next_event_kind: str | None,
    days_since_event: int | None,
    days_to_nearest_opex: int | None,
    iv_rank_change_1d: float | None,
    gap_pct: float | None,
) -> MarketStateResult:
    """Run `engine.market_state.classify()` per plan §9.2 + §22.3.

    Pure wrapper — no DB, no persistence. The 18 §22.3 inputs flow in
    via kwargs to keep the engine call call-site identical to the
    direct engine usage.
    """
    return classify(
        spot=spot,
        iv_rank=iv_rank,
        iv_percentile=iv_percentile,
        hv_30=hv_30,
        expected_move_pct=expected_move_pct,
        max_pain=max_pain,
        pcr_volume=pcr_volume,
        pcr_oi=pcr_oi,
        days_to_next_event=days_to_next_event,
        next_event_kind=next_event_kind,
        trend_strength=trend_strength,
        realized_vs_implied=realized_vs_implied,
        days_since_event=days_since_event,
        days_to_nearest_opex=days_to_nearest_opex,
        iv_rank_change_1d=iv_rank_change_1d,
        gap_pct=gap_pct,
        breakout_signal=breakout_signal,
        oi_concentration_at_max_pain=oi_concentration_at_max_pain,
    )


def run_flow_score(
    *,
    chain_snapshot: ChainSnapshot,
    spot: float,
    expiry_focus: Sequence[date],
    dte_to_nearest_opex: int | None = None,
    risk_free_rate: float = 0.05,
    dividend_yield: float = 0.0,
) -> FlowScore:
    """Run `engine.flow_score.compute()` per plan §9.3a V1 contract.

    Pure wrapper — no DB, no persistence. Returns the LOCKED V1
    `FlowScore` contract (§22.2): score / bullish_score / bearish_score
    / bias / recommended_action / pin_probability / gamma_risk /
    gamma_sign / confidence / explanation / breakdown.

    The engine's `compute()` does NOT take a profile — the V1
    decision tree determines `recommended_action` from score /
    gamma_risk / pin_probability only. The M1.15 dev spec's claim
    that `profile` was an input was wrong; the engine wins.
    """
    return flow_score_compute(
        chain_snapshot=chain_snapshot,
        spot=spot,
        expiry_focus=expiry_focus,
        dte_to_nearest_opex=dte_to_nearest_opex,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
    )


# ----------------------------------------------------------------------
# M1.16 — strike + execution standalone wrappers
# ----------------------------------------------------------------------


def run_strike_candidates(
    *,
    action: Action,
    chain_snapshot: ChainSnapshot,
    risk_free_rate: float = 0.05,
    dividend_yield: float = 0.0,
) -> StrikeSelection:
    """Run `engine.strike_selector.select_strikes()` per plan §9.4.

    Pure wrapper — no DB, no persistence. The engine delta-matches
    contracts against `action.parameters.target_delta`, DTE-matches
    against `target_dte`, and returns zero or more `StrikeLeg`s
    wrapped in a `StrikeSelection`.

    Dev-spec deviation noted in `docs/phased-design/phase-1/
    m1.16-strike-execution-endpoints.md`: the spec adapted to the
    engine's real `Action`-driven contract rather than plan §9.4's
    `intent`-driven idea (same pattern as M1.15's flow_score).
    """
    return select_strikes(
        action=action,
        chain_snapshot=chain_snapshot,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
    )


def run_execution_check(
    *,
    legs: Sequence[StrikeLeg],
    quantities: Sequence[int] | None = None,
) -> Execution:
    """Run `engine.execution.assess()` per plan §9.8.

    Pure wrapper — no DB, no persistence. Empty `legs` tuple is valid
    (REDUCE_COVERAGE / MONETIZE_PUT / NO_OP shapes); the engine returns
    an aggregate-only `Execution` in that case.
    """
    return assess(legs=legs, quantities=quantities)
