"""Request/response Pydantic shapes for the M1.14 `/engine/*` endpoints.

Per plan v1.2 §7 (DailyPlanRequest / RecommendRequest) and §17 M1.14.

V1 design choice: until the data-import endpoints land (M1.15+ for
upstream-engine compute, M1.17 for CSV upload of positions/chain/IV),
the `POST /engine/daily-plan` endpoint accepts a hydrated `inputs`
bundle in the request body. This makes the endpoint testable in
isolation. When M1.15+ ships, `inputs` becomes optional and the API
service hydrates from Postgres rows when omitted.

The response is typed loosely as `dict[str, Any]` for V1 — see
`schemas/engine.py` for the rationale. M1.18+ can tighten the
response schema when the Today screen needs strict TS codegen.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from engine.profiles import UserStrategyProfile
from engine.types import ChainSnapshot
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.engine import FlowScoreModel, MarketStateResultModel, PositionStateModel

# ----------------------------------------------------------------------
# Engine input bundle (V1 — full hydrated state in the request body)
# ----------------------------------------------------------------------


class EngineInputs(BaseModel):
    """Full hydrated engine input bundle for the V1 endpoints.

    Mirrors plan §9.6's `EngineInputs` shape. Carries everything
    `produce_daily_decision()` needs:

      - `chain_snapshot`: the M0.6 ChainSnapshot Pydantic model
      - `positions`: PositionState shape (M1.9)
      - `profile`: UserStrategyProfile (M0.6, extended M1.9)
      - `market_state`: MarketStateResult shape (M1.4)
      - `flow_score`: FlowScore shape (M1.5b)

    All fields are required in V1. Future versions (M1.15+) will
    accept partial bundles and hydrate the rest from Postgres.
    """

    model_config = ConfigDict(extra="forbid")

    chain_snapshot: ChainSnapshot
    positions: PositionStateModel
    profile: UserStrategyProfile
    market_state: MarketStateResultModel
    flow_score: FlowScoreModel


# ----------------------------------------------------------------------
# /engine/daily-plan
# ----------------------------------------------------------------------


class DailyPlanRequest(BaseModel):
    """Request body for `POST /engine/daily-plan`.

    Per plan §7 (V1 shape) — but accepts an explicit `inputs` bundle
    until M1.15+ hydrates upstream engines and M1.17 hydrates the
    position / chain rows. `persist=True` is the production default
    (writes a `daily_decisions` row); `persist=False` is the M1.16
    `/engine/what-if` semantics (transient run).
    """

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(default="MSFT", min_length=1, max_length=10)
    as_of: datetime | None = Field(
        default=None,
        description="Decision-time timestamp. Defaults to server `now()` when omitted.",
    )
    inputs: EngineInputs
    persist: bool = Field(
        default=True,
        description="Persist a `daily_decisions` row. Set False for transient runs.",
    )


# ----------------------------------------------------------------------
# /engine/recommend
# ----------------------------------------------------------------------


class RecommendRequest(BaseModel):
    """Request body for `POST /engine/recommend`.

    Per plan §7 (V1 shape). Unlike `/engine/daily-plan`, this endpoint
    runs ONLY the M1.9 `recommend()` step — no strike selection, no
    execution feasibility, no two-stage composer, no persistence. The
    response is the `RecommendationResult` projected to JSON.

    Use cases:
      - UI drill-down: "what would the rule pipeline say without
        execution feedback?"
      - Debugging: isolate rule-matching from downstream noise.
    """

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(default="MSFT", min_length=1, max_length=10)
    market_state: MarketStateResultModel
    flow_score: FlowScoreModel
    positions: PositionStateModel
    profile: UserStrategyProfile


# ----------------------------------------------------------------------
# Response shapes
# ----------------------------------------------------------------------


class DailyDecisionResponse(BaseModel):
    """Response envelope for `POST /engine/daily-plan`.

    `decision` carries the full `DailyDecision` payload as a JSON-clean
    dict (see `engine.decision_to_jsonable_dict`). `is_new_row` is True
    when the persistence layer inserted a fresh row, False when an
    existing row with the same `(user_id, inputs_hash)` was returned
    via `ON CONFLICT DO NOTHING` (idempotent retry).
    """

    decision: dict[str, Any]
    is_new_row: bool


class RecommendResponse(BaseModel):
    """Response envelope for `POST /engine/recommend`.

    `recommendation` carries the `RecommendationResult` JSON projection.
    No persistence — no `is_new_row` flag.
    """

    recommendation: dict[str, Any]
