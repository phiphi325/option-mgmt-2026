"""Pydantic projections of engine input/output types for the API surface.

The engine ships frozen dataclasses for its V1 contracts (per ADR-0005);
the API layer projects them into Pydantic for request validation +
OpenAPI schema generation.

### Input shapes

`PositionStateModel`, `MarketStateResultModel`, `FlowScoreModel` are the
three engine dataclasses that the API receives in request bodies (V1 —
until the data-import endpoints in M1.15+/M1.17 hydrate them from
Postgres). Each carries a `to_engine()` method that returns the matching
engine dataclass.

`ChainSnapshot`, `OptionContract`, and `UserStrategyProfile` are ALREADY
Pydantic models in the engine package (per `packages/engine/engine/types.py`
and `packages/engine/engine/profiles.py`) — they're re-exported here for
documentation but used directly.

### Output / serialization

`DailyDecision` (M1.13) is a frozen dataclass with 20 fields, many of
them nested dataclasses (MarketStateResult, FlowScore, Recommendation
Result, etc.). Rather than define ~15 nested Pydantic shells, the API
serializes the engine output via the `decision_to_jsonable_dict()`
helper. The OpenAPI response schema is intentionally loose
(`dict[str, Any]`) for V1; M1.18+ tightens it when the Today screen
needs typed client codegen.

This split keeps the API contract explicit on input validation (where
typing matters for client error messages) and pragmatic on output
serialization (where the engine's dataclasses are already the
source-of-truth shape).

### M1.16a additions

`CollarBuilderRequest`, `CollarLegResponse`, and `CollarStructureResponse`
expose the collar builder engine module (M1.11a) as a typed API surface.
`CollarStructureResponse.from_engine()` projects the engine's frozen
`CollarStructure` dataclass into the Pydantic response shape.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from enum import Enum
from typing import Any, Literal

from engine.collar_builder import CollarIntent
from engine.flow_score.types import Bias, FlowScore, RecommendedAction
from engine.market_state.classify import MarketStateResult
from engine.recommendation.types import PositionState
from engine.regimes import Regime
from pydantic import BaseModel, ConfigDict, Field

# ----------------------------------------------------------------------
# Input projections (Pydantic → engine dataclass)
# ----------------------------------------------------------------------


class PositionStateModel(BaseModel):
    """Pydantic projection of `engine.recommendation.PositionState`.

    All fields default to "no position" so a minimal request body can
    omit them entirely. Matches the engine dataclass field-for-field.
    """

    model_config = ConfigDict(extra="forbid")

    underlying_shares: int = Field(default=0, ge=0)
    has_short_call: bool = False
    nearest_short_call_strike: float | None = None
    nearest_short_call_dte: int | None = None
    short_call_contracts: int = 0
    has_long_put: bool = False
    long_put_pnl_pct: float = 0.0
    has_short_put: bool = False

    def to_engine(self) -> PositionState:
        return PositionState(
            underlying_shares=self.underlying_shares,
            has_short_call=self.has_short_call,
            nearest_short_call_strike=self.nearest_short_call_strike,
            nearest_short_call_dte=self.nearest_short_call_dte,
            short_call_contracts=self.short_call_contracts,
            has_long_put=self.has_long_put,
            long_put_pnl_pct=self.long_put_pnl_pct,
            has_short_put=self.has_short_put,
        )


class MarketStateResultModel(BaseModel):
    """Pydantic projection of `engine.market_state.MarketStateResult`.

    The full §22.3 18-input result. `all_scores` maps each `Regime` to its
    classifier-side raw score; `tags` is the variable-length annotation list.
    """

    model_config = ConfigDict(extra="forbid")

    regime: Regime
    regime_score: float = Field(ge=0.0, le=1.0)
    all_scores: dict[Regime, float] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    spot: float = Field(gt=0.0)
    iv_rank: float = Field(ge=0.0, le=1.0)
    iv_percentile: float = Field(ge=0.0, le=1.0)
    hv_30: float = Field(ge=0.0)
    expected_move_pct: float = Field(ge=0.0)
    max_pain: float = Field(gt=0.0)
    max_pain_delta_pct: float
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

    def to_engine(self) -> MarketStateResult:
        return MarketStateResult(
            regime=self.regime,
            regime_score=self.regime_score,
            all_scores=dict(self.all_scores),
            tags=tuple(self.tags),
            spot=self.spot,
            iv_rank=self.iv_rank,
            iv_percentile=self.iv_percentile,
            hv_30=self.hv_30,
            expected_move_pct=self.expected_move_pct,
            max_pain=self.max_pain,
            max_pain_delta_pct=self.max_pain_delta_pct,
            pcr_volume=self.pcr_volume,
            pcr_oi=self.pcr_oi,
            trend_strength=self.trend_strength,
            realized_vs_implied=self.realized_vs_implied,
            breakout_signal=self.breakout_signal,
            oi_concentration_at_max_pain=self.oi_concentration_at_max_pain,
            days_to_next_event=self.days_to_next_event,
            next_event_kind=self.next_event_kind,
            days_since_event=self.days_since_event,
            days_to_nearest_opex=self.days_to_nearest_opex,
            iv_rank_change_1d=self.iv_rank_change_1d,
            gap_pct=self.gap_pct,
        )


class FlowScoreModel(BaseModel):
    """Pydantic projection of `engine.flow_score.FlowScore`.

    Mirrors the V1 LOCKED contract (plan §22.2). `breakdown` is the
    13-key per-component dict (`bullish_dist`, `bullish_call_vol`, etc.).
    """

    model_config = ConfigDict(extra="forbid")

    score: float = Field(ge=-100.0, le=100.0)
    bullish_score: float = Field(ge=0.0, le=100.0)
    bearish_score: float = Field(ge=0.0, le=100.0)
    bias: Bias
    recommended_action: RecommendedAction
    pin_probability: float = Field(ge=0.0, le=1.0)
    gamma_risk: float = Field(ge=0.0, le=1.0)
    gamma_sign: int = Field(ge=-1, le=1)
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: str = ""
    breakdown: dict[str, float] = Field(default_factory=dict)

    def to_engine(self) -> FlowScore:
        return FlowScore(
            score=self.score,
            bullish_score=self.bullish_score,
            bearish_score=self.bearish_score,
            bias=self.bias,
            recommended_action=self.recommended_action,
            pin_probability=self.pin_probability,
            gamma_risk=self.gamma_risk,
            gamma_sign=self.gamma_sign,
            confidence=self.confidence,
            explanation=self.explanation,
            breakdown=dict(self.breakdown),
        )


# ----------------------------------------------------------------------
# Output serialization helper
# ----------------------------------------------------------------------


def to_jsonable(value: Any) -> Any:
    """Recursively project an engine-side object to a JSON-clean Python value.

    Handles every Python type the engine produces:
      - None, bool, int, float, str           passthrough (StrEnum hits str)
      - date / datetime                       ISO-8601 string
      - Enum (non-string)                     `.value`
      - Pydantic BaseModel                    `model_dump(mode="json")`
      - frozen dataclass                      dict of `to_jsonable(field)`
      - dict / Mapping                        dict of `to_jsonable(value)`
      - tuple / list / set / frozenset        list of `to_jsonable(item)`
      - anything else                         `repr(value)` fallback

    The output is safe to pass to `json.dumps()` or to Pydantic
    `JSONResponse`. Mirrors `engine.decision.hashing._canonical()` in
    spirit but does NOT sort dict keys (the response order matches the
    declared field order for human readability).
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.isoformat() + "Z"
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            f.name: to_jsonable(getattr(value, f.name))
            for f in dataclasses.fields(value)
        }
    if isinstance(value, Mapping):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((to_jsonable(item) for item in value), key=repr)
    return repr(value)


def decision_to_jsonable_dict(decision: Any) -> dict[str, Any]:
    """Project a `DailyDecision` (or any frozen dataclass) to a JSON-clean dict.

    Typed loosely (`Any` input, `dict[str, Any]` output) because the
    output Pydantic schema is intentionally `dict` for V1 — see this
    module's docstring.
    """
    result = to_jsonable(decision)
    if not isinstance(result, dict):
        # `decision_to_jsonable_dict` is documented to take a dataclass-shaped
        # value; falling through to fallback indicates a programming error.
        raise TypeError(
            f"decision_to_jsonable_dict expected a dataclass; got {type(decision).__name__}"
        )
    return result


# ----------------------------------------------------------------------
# M1.16a — Collar Builder request / response schemas
# ----------------------------------------------------------------------


class CollarBuilderRequest(BaseModel):
    """Request body for POST /engine/collar-builder.

    Per plan §7 + §22.11 H5.

    Note: `underlying_qty` is intentionally absent — it is resolved from
    the DB at the service layer (§22.11 H5) to prevent callers from
    bypassing the position-ownership check.
    """

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(
        default="MSFT",
        description="Underlying ticker. Phase 1: 'MSFT' only.",
    )
    intents: list[CollarIntent] = Field(
        default=[CollarIntent.ZERO_COST, CollarIntent.INCOME, CollarIntent.DEFENSIVE],
        description=(
            "Collar intents to build. Result list is intent-ordered "
            "(ZERO_COST → INCOME → DEFENSIVE); infeasible intents are omitted."
        ),
    )
    coverage_ratio: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Fraction of position to collar. Defaults to "
            "profile.max_coverage_pct when None."
        ),
    )
    horizon_days: int | None = Field(
        default=None,
        ge=1,
        le=120,
        description=(
            "Max DTE for candidate expiries. Defaults to 45 days "
            "(collar_builder.DEFAULT_HORIZON_DAYS) when None."
        ),
    )


class CollarLegResponse(BaseModel):
    """API projection of `engine.collar_builder.CollarLeg`.

    All numeric fields are float (matching the engine's representation).
    `premium` sign convention: positive = debit paid by user (BUY side),
    negative = credit received (SELL side). Per-share.
    """

    kind: Literal["PUT", "CALL"]
    side: Literal["BUY", "SELL"]
    strike: float
    expiry: date
    qty: int
    delta: float
    iv: float
    bid: float
    ask: float
    mid: float
    premium: float


class CollarStructureResponse(BaseModel):
    """API projection of `engine.collar_builder.CollarStructure`.

    Includes the full confidence breakdown and execution assessment that
    `build()` computes internally. The `score` field is the tie-break
    ranking score within a single intent (NOT the overall confidence).

    P&L fields (`net_debit_credit`, `max_gain`, `max_loss`, breakevens)
    are per-share floats. Multiply by `long_put.qty * 100` for
    position-level dollar amounts.
    """

    name: str
    intent: CollarIntent
    horizon_days: int
    long_put: CollarLegResponse
    short_call: CollarLegResponse
    net_debit_credit: float
    max_gain: float
    max_loss: float
    upside_breakeven: float
    downside_breakeven: float
    capped_upside_pct: float
    protected_downside_pct: float
    confidence: float
    confidence_breakdown: dict[str, Any]
    rationale: list[str]
    risks: list[str]
    invalidation: list[str]
    execution: dict[str, Any]
    score: float = 0.0

    @classmethod
    def from_engine(cls, s: Any) -> CollarStructureResponse:
        """Project an engine `CollarStructure` frozen dataclass → this model.

        Uses `to_jsonable()` for nested dataclasses (`confidence_breakdown`,
        `execution`) so all engine types (enums, dates, nested dataclasses)
        are serialized recursively.
        """

        def _leg(leg: Any) -> CollarLegResponse:
            return CollarLegResponse(
                kind=leg.kind,
                side=leg.side,
                strike=float(leg.strike),
                expiry=leg.expiry,
                qty=int(leg.qty),
                delta=float(leg.delta),
                iv=float(leg.iv),
                bid=float(leg.bid),
                ask=float(leg.ask),
                mid=float(leg.mid),
                premium=float(leg.premium),
            )

        return cls(
            name=s.name,
            intent=s.intent,
            horizon_days=int(s.horizon_days),
            long_put=_leg(s.long_put),
            short_call=_leg(s.short_call),
            net_debit_credit=float(s.net_debit_credit),
            max_gain=float(s.max_gain),
            max_loss=float(s.max_loss),
            upside_breakeven=float(s.upside_breakeven),
            downside_breakeven=float(s.downside_breakeven),
            capped_upside_pct=float(s.capped_upside_pct),
            protected_downside_pct=float(s.protected_downside_pct),
            confidence=float(s.confidence),
            confidence_breakdown=to_jsonable(s.confidence_breakdown),
            rationale=list(s.rationale),
            risks=list(s.risks),
            invalidation=list(s.invalidation),
            execution=to_jsonable(s.execution),
            score=float(getattr(s, "score", 0.0)),
        )


__all__ = [
    "CollarBuilderRequest",
    "CollarLegResponse",
    "CollarStructureResponse",
    "FlowScoreModel",
    "MarketStateResultModel",
    "PositionStateModel",
    "decision_to_jsonable_dict",
    "to_jsonable",
]


# Convenience re-exports so callers can import all engine input shapes from one place.
# (The Pydantic models in the engine package are already JSON-clean.)
_re_exports: Sequence[str] = ()  # for completeness; reserved for future re-exports
