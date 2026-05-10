"""Shared option-chain primitives used across the engine.

These are the input shapes for every scoring + decision function. Per plan
v1.2 §10 + ADR-0005, the data layer (apps/api/app/services/chain_service.py,
M1+) hydrates a ChainSnapshot from Postgres + provider data and passes it
into the engine. The engine never touches the wire or the DB.

ChainSnapshot is intentionally narrow — only the fields the engine reads.
Display-only fields (delta, gamma, theta, vega) are computed lazily from
greeks where needed. See plan v1.2 §6 (Postgres schema) for the persisted
shape; the in-memory snapshot is a projection, not a 1:1 mirror.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class OptionType(StrEnum):
    """Call or put. Matches the Postgres `option_type` enum (apps/api/app/db/migrations/versions/0001_init.py)."""

    CALL = "CALL"
    PUT = "PUT"


class OptionContract(BaseModel):
    """A single option-chain row at a fixed observation time.

    All prices are in USD per share (NOT per contract); multiplier handling
    happens in the API layer. Implied vol is in 0..1 space (0.35 = 35% IV).
    """

    model_config = ConfigDict(frozen=True)

    underlying: str = Field(min_length=1, max_length=10)  # e.g. "MSFT"
    expiry: date
    strike: float = Field(gt=0.0)
    option_type: OptionType

    # Mid-quote derived from bid/ask. None when both bid and ask are missing
    # (illiquid contract); the engine downweights these via execution feasibility.
    mid: float | None = Field(default=None, ge=0.0)
    bid: float | None = Field(default=None, ge=0.0)
    ask: float | None = Field(default=None, ge=0.0)

    # Implied vol (0..1+). Greater than 1 is rare but legal (e.g. event-driven extremes).
    iv: float | None = Field(default=None, ge=0.0)

    # Open interest + volume. Used for liquidity filtering.
    open_interest: int = Field(ge=0)
    volume: int = Field(ge=0)


class ChainSnapshot(BaseModel):
    """A point-in-time option chain projection used by the engine.

    Frozen — once constructed, the snapshot is immutable, making it safe to
    hash for `inputs_hash` and safe to share across scoring functions without
    defensive copies.
    """

    model_config = ConfigDict(frozen=True)

    underlying: str = Field(min_length=1, max_length=10)
    spot: float = Field(gt=0.0)
    as_of: date

    # Tuple-of-frozen-models is the closest immutable container Pydantic
    # supports natively. Engine code MUST treat this as read-only.
    contracts: tuple[OptionContract, ...]
