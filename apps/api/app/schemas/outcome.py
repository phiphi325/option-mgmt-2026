"""Request/response shapes for `/outcomes` endpoints (M1.17).

Per plan v1.2 §7 + §9.10 + §17 M1.17 + the M1.17 dev spec.

Endpoints:
  GET    /outcomes?since=ISO&limit=N&cursor=…   → OutcomeListResponse
  POST   /outcomes                              → OutcomeResponse
  PATCH  /outcomes/{id}                         → OutcomeResponse

Schema mirrors the `outcomes` table from 0001_init.py with two
clarifications:

  1. `daily_decision_id` is UNIQUE on the table (PK-via-FK pattern from
     §6). The service layer surfaces this as 409 on duplicate POST
     rather than letting it bubble up as a 500 IntegrityError.
  2. `source` is server-set (`"manual"` for POST; `"auto"` reserved for
     M3.5 auto-fill). Not in the request schema.

Cursor pagination: V1 implementation uses opaque base64-encoded cursors
encoding the `(evaluated_at, id)` tuple of the last row in the previous
page. The dev spec calls for cursor pagination over `(evaluated_at DESC,
id DESC)`; the encoding is private and clients should treat
`next_cursor` as opaque.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ----------------------------------------------------------------------
# Enum literals — mirror the Postgres enum types from 0001_init.py
# ----------------------------------------------------------------------

OutcomeQuality = Literal["good", "neutral", "bad"]
OutcomeError = Literal[
    "early_roll",
    "late_roll",
    "missed_breakout",
    "over_coverage",
    "under_coverage",
    "wrong_strike",
    "ignored_event",
    "none",
]
OutcomeSource = Literal["manual", "auto"]
Regime = Literal[
    "HIGH_IV_EVENT",
    "HIGH_IV_PIN",
    "LOW_IV_TREND",
    "LOW_IV_RANGE",
    "BREAKOUT",
    "POST_EVENT_REPRICE",
]


# ----------------------------------------------------------------------
# Response — flat shape mirroring the outcomes table
# ----------------------------------------------------------------------


class OutcomeResponse(BaseModel):
    """Single outcome row, JSON-serialized.

    `daily_decision_id` is the FK + UNIQUE; same UUID never appears
    twice in this list. `evaluated_at` defaults server-side at insert
    time.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID
    daily_decision_id: UUID
    evaluated_at: datetime
    horizon_days: int = Field(ge=1)
    pnl_realized: Decimal | None = None
    pnl_unrealized: Decimal | None = None
    decision_quality: OutcomeQuality | None = None
    error_type: OutcomeError
    actual_regime_realized: Regime | None = None
    regime_match: bool | None = None
    notes: str | None = None
    source: OutcomeSource


# ----------------------------------------------------------------------
# Request bodies
# ----------------------------------------------------------------------


class OutcomeCreateRequest(BaseModel):
    """POST /outcomes body — `source` is server-set, not accepted here."""

    model_config = ConfigDict(extra="forbid")

    daily_decision_id: UUID
    horizon_days: int = Field(ge=1)
    pnl_realized: Decimal | None = None
    pnl_unrealized: Decimal | None = None
    decision_quality: OutcomeQuality | None = None
    error_type: OutcomeError = "none"
    actual_regime_realized: Regime | None = None
    regime_match: bool | None = None
    notes: str | None = None


class OutcomePatchRequest(BaseModel):
    """PATCH /outcomes/{id} body — all fields optional; `source` is immutable
    after insert (manual stays manual; auto-fill happens via a separate path
    in M3.5).
    """

    model_config = ConfigDict(extra="forbid")

    horizon_days: int | None = Field(default=None, ge=1)
    pnl_realized: Decimal | None = None
    pnl_unrealized: Decimal | None = None
    decision_quality: OutcomeQuality | None = None
    error_type: OutcomeError | None = None
    actual_regime_realized: Regime | None = None
    regime_match: bool | None = None
    notes: str | None = None


# ----------------------------------------------------------------------
# List response — cursor-paginated
# ----------------------------------------------------------------------


class OutcomeListResponse(BaseModel):
    """GET /outcomes response. `next_cursor` is opaque; pass it back as
    `?cursor=…` to fetch the next page.
    """

    model_config = ConfigDict(extra="forbid")

    outcomes: list[OutcomeResponse]
    next_cursor: str | None = None


__all__ = [
    "OutcomeCreateRequest",
    "OutcomeListResponse",
    "OutcomePatchRequest",
    "OutcomeResponse",
]
