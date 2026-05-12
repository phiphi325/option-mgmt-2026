"""Request/response Pydantic shapes for the `/engine/*` endpoints.

Per plan v1.2 §7 (canonical endpoint table), §22.14 (what-if non-
persistence), §17 M1.14 + M1.15.

V1 design choice: until the data-import endpoints land in M1.17, every
`/engine/*` endpoint accepts a fully hydrated bundle in the request
body. This makes the endpoints testable in isolation. After M1.17,
the relevant fields become optional and the API service hydrates from
Postgres rows when omitted.

Response shapes are typed loosely as `dict[str, Any]` for V1 — see
`schemas/engine.py` for the rationale. M1.18+ can tighten them when
the Today screen needs strict TS codegen.

M1.15 additions (this file's lower half):
  - WhatIfRequest        — body for POST /engine/what-if (§22.14 non-persisting)
  - MarketStateRequest   — body for POST /engine/market-state (§9.2 + §22.3)
  - FlowScoreRequest     — body for POST /engine/flow-score (§9.3a V1 contract)
  - WhatIfResponse       — envelope with `is_new_row: Literal[False]`
  - MarketStateResponse  — envelope with `market_state: dict`
  - FlowScoreResponse    — envelope with `flow_score: dict`
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

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


# ----------------------------------------------------------------------
# /engine/what-if (M1.15)
# ----------------------------------------------------------------------


class WhatIfRequest(BaseModel):
    """Request body for `POST /engine/what-if`.

    Per plan §7 (V1 shape) and §22.14 (explicit non-persistence).

    Identical body to `DailyPlanRequest` minus the `persist` toggle
    (what-if NEVER persists), plus an `overrides` dict that mutates the
    `inputs.market_state` projection before the engine runs. The
    canonical example from §7 (`{"spot": 425.00, "iv_rank": 35}`) uses
    flat keys mapping to MarketStateResultModel fields.

    Override semantics:
      - Keys must match `MarketStateResultModel.model_fields`.
      - Unknown keys raise 422 at the application layer (better error
        message than a Pydantic ValidationError downstream).
      - Values that fail the model's range constraints (e.g. iv_rank > 1)
        bubble up as the standard Pydantic 422.
      - To mutate non-market_state state (positions, chain, profile),
        pass an already-modified `inputs` bundle. The flat `overrides`
        shortcut is intentionally scoped to market_state for V1 — that's
        what the §7 example targets and where the actionable
        what-if knobs (spot, iv_rank, regime, etc.) live.
    """

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(default="MSFT", min_length=1, max_length=10)
    as_of: datetime | None = Field(
        default=None,
        description="Decision-time timestamp. Defaults to server `now()` when omitted.",
    )
    inputs: EngineInputs
    overrides: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Flat overrides on inputs.market_state.* fields. "
            "Example: {'spot': 425.0, 'iv_rank': 0.35}. "
            "See class docstring for semantics."
        ),
    )


class WhatIfResponse(BaseModel):
    """Response envelope for `POST /engine/what-if`.

    Symmetric to `DailyDecisionResponse` but `is_new_row` is always
    `False` — what-if explicitly does not persist (§22.14). Carrying
    the field keeps client code that handles `DailyDecisionResponse`
    uniformly able to also handle what-if responses.
    """

    decision: dict[str, Any]
    is_new_row: Literal[False] = False


# ----------------------------------------------------------------------
# /engine/market-state (M1.15)
# ----------------------------------------------------------------------


class MarketStateRequest(BaseModel):
    """Request body for `POST /engine/market-state`.

    Per plan §9.2 + §22.3 — runs `engine.market_state.classify()`
    only. All 18 §22.3 inputs are required (no service-layer hydration
    in V1 — M1.17+ accepts a thinner body and hydrates from Postgres).

    Scale conventions (echo from engine.market_state.classify):
      - iv_rank, iv_percentile, trend_strength, breakout_signal,
        oi_concentration_at_max_pain: [0, 1]
      - iv_rank_change_1d: [-1, 1]
      - gap_pct, expected_move_pct: fractions of spot
      - spot, max_pain: dollars (float)
    """

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(default="MSFT", min_length=1, max_length=10)
    spot: float = Field(gt=0.0)
    iv_rank: float = Field(ge=0.0, le=1.0)
    iv_percentile: float = Field(ge=0.0, le=1.0)
    hv_30: float = Field(ge=0.0)
    expected_move_pct: float = Field(ge=0.0)
    max_pain: float = Field(gt=0.0)
    pcr_volume: float = Field(ge=0.0)
    pcr_oi: float = Field(ge=0.0)
    trend_strength: float = Field(ge=0.0, le=1.0)
    realized_vs_implied: float = Field(ge=0.0)
    breakout_signal: float = Field(ge=0.0, le=1.0)
    oi_concentration_at_max_pain: float = Field(ge=0.0, le=1.0)
    days_to_next_event: int | None = None
    next_event_kind: str | None = None
    days_since_event: int | None = None
    days_to_nearest_opex: int | None = None
    iv_rank_change_1d: float | None = None
    gap_pct: float | None = None


class MarketStateResponse(BaseModel):
    """Response envelope for `POST /engine/market-state`.

    `market_state` carries the full `MarketStateResult` JSON projection
    (all 18 inputs echoed + `regime`, `regime_score`, `all_scores`,
    `tags`, `max_pain_delta_pct`).
    """

    market_state: dict[str, Any]


# ----------------------------------------------------------------------
# /engine/flow-score (M1.15)
# ----------------------------------------------------------------------


class FlowScoreRequest(BaseModel):
    """Request body for `POST /engine/flow-score`.

    Per plan §9.3a V1 contract — runs `engine.flow_score.compute()`
    only. The engine's `compute()` signature does NOT take a profile
    (the M1.5b implementation determines `recommended_action` without
    profile.style — the V1 decision tree uses only score / gamma_risk /
    pin_probability). This deviates from `docs/phased-design/phase-1/
    m1.15-engine-readonly-endpoints.md` Request schemas section, which
    erroneously listed `profile` as a request field; the actual engine
    contract wins (§9.3a is the source of truth).
    """

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(default="MSFT", min_length=1, max_length=10)
    chain_snapshot: ChainSnapshot
    spot: float = Field(gt=0.0)
    expiry_focus: list[date] = Field(min_length=1)
    dte_to_nearest_opex: int | None = Field(default=None, ge=0)
    risk_free_rate: float = Field(default=0.05, ge=0.0, le=1.0)
    dividend_yield: float = Field(default=0.0, ge=0.0, le=1.0)


class FlowScoreResponse(BaseModel):
    """Response envelope for `POST /engine/flow-score`.

    `flow_score` carries the full V1 LOCKED contract (§9.3a / §22.2):
    score, bullish_score, bearish_score, bias, recommended_action,
    pin_probability, gamma_risk, gamma_sign, confidence, explanation,
    breakdown.
    """

    flow_score: dict[str, Any]
