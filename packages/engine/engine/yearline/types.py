"""`YearlineContext` — the gated statistical-context value object (OM-Y1).

Per ADR-0009 and `docs/enhancements/0002-yearline-context-assessment.md`. This is
the *consumer-side* mirror of yearline-universe's V13.8 adapter output
(`adapter_version = "v13_8_yearline_context_adapter_v1"`): a lightweight, flat,
JSON-serializable value object hydrated in the jobs/ingestion layer (OM-Y2) and —
from OM-Y4 — optionally consumed by the pure engine, ONLY where its trust gate
passes.

The engine never imports yearline-universe (ADR-0005). The coupling is this
versioned value object, parsed from a persisted artifact — exactly how
`MarketStateResult` / `FlowScore` are hydrated today.

**Gate-respect (the hard rule).** Consume `p_retry[h]` only where `gate_passed[h]`
is `True`; consume `p_success` / `p_successful_reclaim[h]` only where
`success_gate_passed`. `repair_active is False` ⇒ `p_retry == {}` (dormant above
the yearline — read `post_confirmation_trend_state` instead). `is_stale is True`
⇒ treat as no-usable-context.

**OM-Y1 ships no behaviour change.** This module only defines and pins the
contract; the engine does not yet consume it (that is OM-Y4). `extra="forbid"`
makes an un-pinned producer-side field-shape change fail loudly in the contract
test — the cross-repo drift guard ADR-0009 calls for.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Accepted producer-contract version range. A yearline release that bumps
# `adapter_version` beyond this set is treated as incompatible and requires a
# coordinated OM-Y1 pin bump (+ a fixtures refresh). Pinned per ADR-0009.
ACCEPTED_ADAPTER_VERSIONS: frozenset[str] = frozenset(
    {"v13_8_yearline_context_adapter_v1"}
)
ACCEPTED_SCHEMA_VERSIONS: frozenset[str] = frozenset(
    {"v13_single_ticker_statistical_context_envelope"}
)


class PRetryBasis(StrEnum):
    """Which surface produced `p_retry` (provenance, for gate-status display)."""

    EMPIRICAL = "empirical"  # the Phase-4 isotonic-gated empirical estimator
    BLEND = "blend"  # the Phase-7 gated classifier blend


class YearlineContext(BaseModel):
    """The subset of yearline-universe's envelope the engine consumes.

    Frozen + `extra="forbid"`: once parsed the object is immutable (safe to fold
    into the replay hash from OM-Y4), and any field the producer adds without a
    coordinated `adapter_version` bump is rejected — surfacing contract drift in
    CI rather than silently ignoring it.

    Horizon-keyed maps (`p_retry`, `gate_passed`, `p_successful_reclaim`) use
    `int` horizon keys (10/20/40/60 days). JSON object keys arrive as strings and
    are coerced to `int` on parse; `model_dump(mode="json")` round-trips them back
    to strings.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # --- identity / provenance (nullable per the V13.8 schema) ---
    as_of: date | None
    ticker: str | None
    schema_version: str | None
    model_stack_version: str | None
    adapter_version: str = Field(min_length=1)

    # --- structural regime ---
    repair_active: bool  # repair/hazard engine active (price below MA250)
    distance_to_ma250_pct: float | None = None  # signed; negative = below
    required_rebound_to_ma250_pct: float | None = None
    post_confirmation_trend_state: str | None = None  # set only when above MA250

    # --- gated retry probability (consume ONLY where gate_passed[h]) ---
    p_retry: dict[int, float] = Field(default_factory=dict)  # {} when dormant
    p_retry_basis: PRetryBasis | None = None
    gate_passed: dict[int, bool] = Field(default_factory=dict)

    # --- conditional timing (descriptive range, not a forecast) ---
    days_to_touch_central: float | None = None
    days_to_touch_low: float | None = None
    days_to_touch_high: float | None = None

    # --- gated success / composite (consume ONLY where success_gate_passed) ---
    p_success: float | None = None
    success_gate_passed: bool = False
    p_successful_reclaim: dict[int, float | None] = Field(default_factory=dict)

    # --- provenance / safety ---
    reference_scope: str | None = None  # empirical bucket scope (sample transparency)
    is_stale: bool
    must_not_auto_execute: Literal[True] = True  # hard invariant — never False
