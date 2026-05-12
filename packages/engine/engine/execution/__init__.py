"""Execution Feasibility Module (M1.11) — liquidity / spread / slippage / fill.

Per plan v1.2 §9.8 (Execution Feasibility Module) and §17 M1.11.

Public surface:

    types:
        Execution, ExecutionLeg, OrderType
    orchestrator:
        assess(*, legs, quantities=None) -> Execution
    composer bridge:
        liquidity_penalty(execution) -> float
    per-component scorers (V1 priors, replaceable per ADR-0008 Phase 4 ML):
        liquidity:
            norm_oi, norm_volume, compute_spread_bps, liquidity_score
        slippage:
            expected_slippage
        fill:
            fill_confidence, suggested_order_type, DOWNGRADE_THRESHOLD
        size:
            tick_size, limit_price_band, size_warnings

`liquidity_penalty()` is the M1.11 → M1.10 hand-off: it maps
`Execution → illiquidity_penalty ∈ [0, 1]` for the Confidence Composer.

`DOWNGRADE_THRESHOLD = 0.50` is the M1.12 trigger — when an aggregate
fill confidence drops below it, the Master Decision Engine (M1.13) will
re-run the Strike Selector with adjusted filters.

ADR-0005 pure-function discipline: this module has no I/O, no clock,
no env access. The data layer (apps/api) hydrates `StrikeLeg`s and
quantities and passes them in.
"""

from __future__ import annotations

from engine.execution.assess import (
    aggregate,
    assess,
    liquidity_penalty,
)
from engine.execution.fill import (
    DOWNGRADE_THRESHOLD,
    fill_confidence,
    suggested_order_type,
)
from engine.execution.liquidity import (
    compute_spread_bps,
    liquidity_score,
    norm_oi,
    norm_volume,
)
from engine.execution.size import (
    limit_price_band,
    size_warnings,
    tick_size,
)
from engine.execution.slippage import expected_slippage
from engine.execution.types import Execution, ExecutionLeg, OrderType

__all__ = [
    "DOWNGRADE_THRESHOLD",
    "Execution",
    "ExecutionLeg",
    "OrderType",
    "aggregate",
    "assess",
    "compute_spread_bps",
    "expected_slippage",
    "fill_confidence",
    "limit_price_band",
    "liquidity_penalty",
    "liquidity_score",
    "norm_oi",
    "norm_volume",
    "size_warnings",
    "suggested_order_type",
    "tick_size",
]
