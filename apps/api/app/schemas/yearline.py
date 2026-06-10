"""Schemas for the yearline evidence panel (OM-Y3).

The scalar `YearlineContext` (the card) is the engine contract
(`engine.yearline.YearlineContext`, OM-Y1) reused verbatim. This module adds:

  - `YearlineTrendSeriesModel` — the **presentation-only** time-series artifact
    (`series_version = v13_8_1_yearline_trend_series_v1`) that powers the trend
    plot. It is NOT an engine input and never enters the replay hash (ADR-0009),
    so it lives in the API schema layer, not `packages/engine`.
  - `YearlinePanelResponse` — what `GET /engine/yearline-context` returns: the
    raw latest context (may be stale — the panel shows staleness honestly) plus
    the latest available trend series (or `None` → the panel renders its empty
    state).

Per ADR-0009 + docs/enhancements/0002-yearline-context-assessment.md +
docs/enhancements/yearline/producer-handoff/ux_trend_plot_support_analysis.md §6.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from engine.yearline import YearlineContext
from pydantic import BaseModel, ConfigDict, Field

# Accepted producer trend-series version range (pinned, like the context's
# ACCEPTED_ADAPTER_VERSIONS). The series version is independent of the scalar
# contract's adapter_version — V13.8.2 docs hardening left it unchanged.
ACCEPTED_SERIES_VERSIONS: frozenset[str] = frozenset(
    {"v13_8_1_yearline_trend_series_v1"}
)


class YearlineTrendSeriesModel(BaseModel):
    """Presentation-only trend series (parallel arrays aligned to `dates`).

    `available: false` is the explicit empty state (`{available, warning,
    series_version, must_not_auto_execute, ...}`) — the panel renders a
    "no trend history" placeholder rather than a blank chart.

    Gated series (`hazard_today`, `p_retry_40d`) and the trend-score series are
    `null` off-regime — the consumer must **gap** the line, never interpolate
    (UX §6.3). Price/MA arrays (`close`/`ma20`/`ma50`/`ma250`) are present only
    when `available`.
    """

    model_config = ConfigDict(extra="forbid")

    available: bool
    series_version: str
    must_not_auto_execute: Literal[True] = True
    warning: str | None = None

    ticker: str | None = None
    as_of: date | None = None
    schema_version: str | None = None
    model_stack_version: str | None = None
    n: int | None = None
    dates: list[str] | None = None

    # percent panel
    distance_to_ma250_pct: list[float | None] | None = None
    drawdown_so_far_pct: list[float | None] | None = None

    # regime bands + trend state (internal identifiers → map to labels in the UI)
    active_engine: list[str | None] | None = None
    post_confirmation_trend_state: list[str | None] | None = None

    # 0-1 trend scores (null while in repair)
    trend_quality: list[float | None] | None = None
    pullback_quality: list[float | None] | None = None
    overextension: list[float | None] | None = None
    deterioration: list[float | None] | None = None

    # 0-1 gated risk (null while in trend)
    hazard_today: list[float | None] | None = None
    p_retry_40d: list[float | None] | None = None

    # price / MA overlay (present only when available)
    close: list[float] | None = None
    ma20: list[float] | None = None
    ma50: list[float] | None = None
    ma250: list[float] | None = None


class YearlinePanelResponse(BaseModel):
    """`GET /engine/yearline-context` — the Today-screen evidence panel payload.

    `context` is the **raw latest** scalar context (may be `is_stale: true`) so
    the panel can show staleness honestly — distinct from the engine-facing
    hydration which abstains on stale (OM-Y2). `trend_series` is the latest
    `available` series, or `None` when none is persisted (empty state).
    """

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1)
    context: YearlineContext | None
    trend_series: YearlineTrendSeriesModel | None
