"""Execution Feasibility V1 contract types.

Per plan v1.2 §7 + §9.8 (Execution Feasibility Module) and §17 M1.11.

The Execution Feasibility Module sits in the cross-cutting band of the
architecture (per §5 layer cake): it takes concrete `StrikeLeg`s from
the M1.7 Strike Selector + per-leg quantities, and produces a per-leg +
aggregate scoring of how realistically the order can be filled.

Two output fields feed downstream consumers directly:

  - `aggregate_fill_confidence` ∈ [0, 1] — feeds the
    `engine.confidence.compose()` formula via the M1.10 `illiquidity_penalty`
    kwarg. The M1.11 `liquidity_penalty(execution)` helper does the
    mapping: `illiquidity_penalty = clip01(1.0 - aggregate_fill_confidence)`.
  - `legs[i].fill_confidence < 0.5` triggers the M1.12 downgrade
    callback (Strike Selector re-run with adjusted filters).

Per ADR-0005 these are frozen dataclasses (consistent with
`StrikeSelection`, `RecommendationResult`, `ConfidenceBreakdown`). The
plan §7 spec uses Pydantic for API-surface schemas — when the M1.16
`/engine/execution-check` endpoint lands the frozen-dataclass output
can be projected into the Pydantic schema (no engine-side serialization
work needed).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class OrderType(StrEnum):
    """Suggested order type for the executed leg.

    `LIMIT` — buyer is patient; place a limit at the suggested band; the
    fill may take time but slippage is bounded by the limit price.

    `MARKETABLE_LIMIT` — buyer wants the fill now; cross the spread but
    cap the slippage with a limit a few ticks beyond the offer.

    Wire-stable values — flow through to API responses and order ticket
    UIs.
    """

    LIMIT = "limit"
    MARKETABLE_LIMIT = "marketable_limit"


@dataclass(frozen=True)
class ExecutionLeg:
    """Per-leg execution-feasibility result.

    Fields (per plan §7 `ExecutionLeg`):
        leg_id:                Stable human-readable identifier built from
                               (side, option_type, strike, expiry). Echoed
                               on logs / UI / API.
        liquidity_score:       [0, 1]. §9.8 formula:
                                 0.4 × norm_oi(OI)
                                 + 0.4 × norm_volume(volume)
                                 + 0.2 × (1 − min(spread_bps, 300)/300)
        spread_bps:            Bid-ask spread in basis points of mid.
                               Floored mid at $0.01 to avoid division by
                               zero on broken quotes; capped at 9999 for
                               extreme outliers.
        fill_confidence:       [0, 1]. §9.8 formula:
                                 clip01(0.6 × liquidity + 0.4 × (1 − spread_bps/300))
        expected_slippage:     Estimated $/contract slippage from mid.
                               V1 prior is half-spread + size-impact term
                               (see `engine.execution.slippage`).
        suggested_order_type:  LIMIT when `fill_confidence ≥ 0.70`,
                               MARKETABLE_LIMIT otherwise.
        limit_price_band:      `(low, high)` suggested limit-order price
                               around mid; band width = 1 US-options tick
                               ($0.01 below $3 mid, $0.05 above).
        size_warnings:         Tuple of human-readable warnings — e.g.
                               "qty exceeds 10% of OI", "qty exceeds 50%
                               of volume".

    Frozen dataclass per ADR-0005.
    """

    leg_id: str
    liquidity_score: float
    spread_bps: int
    fill_confidence: float
    expected_slippage: float
    suggested_order_type: OrderType
    limit_price_band: tuple[float, float]
    size_warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class Execution:
    """Aggregate execution-feasibility result for a multi-leg action.

    Fields (per plan §7 `Execution`):
        aggregate_liquidity_score:   `min(leg.liquidity_score for leg in legs)`.
                                     The weakest leg controls the strategy
                                     (you can't fill a collar's call leg if
                                     the put leg is too thin).
        aggregate_fill_confidence:   `min(leg.fill_confidence for leg in legs)`.
                                     Same weakest-link rule.
        suggested_order_type:        LIMIT when every leg ≥ 0.70 fill,
                                     MARKETABLE_LIMIT otherwise.
        legs:                        Per-leg detail in input order.
        notes:                       Collected `size_warnings` from all legs,
                                     plus a downgrade hint when aggregate
                                     fill is below 0.50 (the M1.12 trigger).

    Empty `legs` is a valid value — REDUCE_COVERAGE, MONETIZE_PUT, NO_OP
    actions produce no new legs and the Execution Feasibility result is
    "trivially fillable" (aggregate scores at 1.0, no warnings).

    Frozen dataclass per ADR-0005.
    """

    aggregate_liquidity_score: float
    aggregate_fill_confidence: float
    suggested_order_type: OrderType
    legs: tuple[ExecutionLeg, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)
