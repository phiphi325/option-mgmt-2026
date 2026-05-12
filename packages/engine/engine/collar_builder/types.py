"""Collar Builder V1 contract types.

Per plan v1.2 §9.10 (Collar Builder — first-class engine module) +
§7 (`CollarIntent` / `CollarLeg` / `CollarStructure` schemas) +
M1.11a dev spec (`docs/phased-design/phase-1/m1.11a-collar-builder-engine.md`).

The engine ships **frozen dataclasses**; the API layer (M1.16a, separate
PR) projects these into Pydantic schemas for JSON serialization to clients.
Field names match 1:1 (no transformation) — consistent with the M1.13
DailyDecision projection pattern.

Floats (not Decimals) are used throughout for compatibility with the
existing `engine.types.OptionContract` shape — see M1.6 (Greeks) +
M1.7 (Strike Selector) which already standardized on float. The API
layer is free to project to Decimal for client wire format if needed.

Frozen dataclasses per [ADR-0005](../../decisions/0005-engine-pure-function-discipline.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Literal

from engine.confidence.types import ConfidenceBreakdown
from engine.execution.types import Execution


class CollarIntent(StrEnum):
    """The three V1 collar variants per plan §9.10.

    Wire-stable values — flow through to Postgres + TypeScript codegen.

    `zero_cost`:  net premium ≈ 0 (within ±$0.10 per share). Short-call
                  premium pays for the long put.
    `income`:     maximize net credit. Closer-to-ATM short call, deeper
                  put (less downside protection in exchange for premium).
    `defensive`:  maximize downside protection. Deeper put, willing to
                  accept a net debit (within ~0.5% of position notional).
    """

    ZERO_COST = "zero_cost"
    INCOME = "income"
    DEFENSIVE = "defensive"


@dataclass(frozen=True)
class CollarLeg:
    """A single leg of a collar — either the long-put or short-call.

    Mirrors plan §7 `CollarLeg` shape. Sign conventions:

      delta:    Signed by `kind` — CALL ∈ (0, 1], PUT ∈ [-1, 0).
      premium:  Signed by `side` — BUY = positive (paid debit),
                SELL = negative (received credit). Per-share.

    The `qty` field is the number of contracts (not shares); each
    contract covers 100 shares.

    Frozen by [ADR-0005].
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


@dataclass(frozen=True)
class CollarStructure:
    """A complete collar candidate — long-put + short-call pair sized
    against an underlying position.

    Mirrors plan §7 `CollarStructure` shape. All P&L fields are
    **per share** (not per-contract, not per-structure) — multiply by
    `long_put.qty * 100` to convert to dollars at the position level.

    Conventions:

      net_debit_credit:    Positive = net debit (paid more for put than
                           received from call). Negative = net credit.
                           Per share.
      max_gain:            At expiry, per share. Excludes stock cost
                           basis — pure structure P&L.
      max_loss:            At expiry, per share. Includes the cost of
                           the put + premium dynamics; the underlying
                           stock loss is separate.
      capped_upside_pct:   (short_call.strike - spot) / spot. The
                           percentage move the stock can make before
                           the short call caps further upside.
      protected_downside_pct:
                           (spot - long_put.strike) / spot. The
                           percentage move down before the put kicks
                           in to floor losses.
      score:               Tie-break score per plan §9.10
                           (iv_score - event_score - illiquidity_penalty).
                           Used only for ranking candidates within a
                           single intent — NOT a confidence score.

    Frozen by [ADR-0005].
    """

    name: str                              # e.g., "Zero-cost 30d collar 405/430"
    intent: CollarIntent
    horizon_days: int
    long_put: CollarLeg
    short_call: CollarLeg
    net_debit_credit: float
    max_gain: float
    max_loss: float
    upside_breakeven: float
    downside_breakeven: float
    capped_upside_pct: float
    protected_downside_pct: float
    confidence: float
    confidence_breakdown: ConfidenceBreakdown
    rationale: tuple[str, ...]
    risks: tuple[str, ...]
    invalidation: tuple[str, ...]
    execution: Execution
    score: float = 0.0
