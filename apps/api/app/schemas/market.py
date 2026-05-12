"""Response shape for `GET /market/{ticker}/latest` (M1.16b, deferred → M1.17).

Per plan v1.2 §7 v1.1 + §22.10 (`MarketLatestSnapshot` data source).

Reads the most-recent chain + iv + hv + event rows for the ticker, then
computes `max_pain`, `pcr_volume`, `pcr_oi`, and `expected_move_pct`
on-the-fly via engine primitives (per §22.10's "computes on the fly,
no engine pipeline call" contract).

Staleness contract (§22.10 thresholds):
  - `chain_age_seconds > 7200`   (2h)  → tag `stale_chain`,  any_stale=true
  - `iv_age_seconds    > 90000`  (~25h) → tag `stale_iv`,     any_stale=true

422 when prerequisites aren't met:
  - `iv_history` for the ticker has < 30 rows  (per §22.10 + §22.12)
  - `option_chain_snapshots` empty for ticker

This endpoint is the convenience read-through powering the Today
screen's header + external integrations that want raw context without
calling `/engine/daily-plan`. It does NOT invoke the engine pipeline,
which is why it was deferrable until M1.17's CSV import populated the
source tables.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DataFreshness(BaseModel):
    """Per-input staleness metadata. Mirrors `DailyDecision.data_freshness`."""

    model_config = ConfigDict(extra="forbid")

    chain_age_seconds: int | None = Field(default=None, ge=0)
    iv_age_seconds: int | None = Field(default=None, ge=0)
    hv_age_seconds: int | None = Field(default=None, ge=0)
    any_stale: bool = False
    stale_tags: list[str] = Field(default_factory=list)


class MarketLatestSnapshotResponse(BaseModel):
    """Snapshot of the most-recent market state for a ticker.

    All fields except `as_of`, `ticker`, `spot`, and `data_freshness`
    may be None when the underlying data is missing or insufficient.
    The service raises 422 before this response shape applies if
    critical prerequisites are absent (iv_history < 30 or chain empty).
    """

    model_config = ConfigDict(extra="forbid")

    as_of: datetime
    ticker: str
    spot: Decimal
    iv_rank: float | None = Field(default=None, ge=0.0, le=1.0)
    iv_percentile: float | None = Field(default=None, ge=0.0, le=1.0)
    hv_30: float | None = Field(default=None, ge=0.0)
    expected_move_pct: float | None = Field(default=None, ge=0.0)
    max_pain: Decimal | None = None
    pcr_volume: float | None = Field(default=None, ge=0.0)
    pcr_oi: float | None = Field(default=None, ge=0.0)
    next_event: dict[str, Any] | None = None
    data_freshness: DataFreshness


__all__ = ["DataFreshness", "MarketLatestSnapshotResponse"]
