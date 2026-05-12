"""Execution Feasibility orchestrator — `assess()` + aggregation + composer bridge.

Per plan v1.2 §9.8 (Execution Feasibility Module) and §17 M1.11.

`assess()` consumes the M1.7 Strike Selector's `StrikeLeg`s (plus
per-leg quantities) and produces an `Execution` result. The function
is pure (per ADR-0005) — no I/O, no clock, no env.

Pipeline per leg:

  1. Read `bid` / `ask` / `mid` / `open_interest` / `volume` from
     the leg's `OptionContract`.
  2. Compute `spread_bps` (`engine.execution.liquidity.compute_spread_bps`).
  3. Compute `liquidity_score` (§9.8 4-component blend).
  4. Compute `expected_slippage` (half-spread + size-impact).
  5. Compute `fill_confidence` (`engine.execution.fill.fill_confidence`).
  6. Compute `limit_price_band` (mid ± 1 tick) and `suggested_order_type`.
  7. Compute `size_warnings` (qty vs. displayed liquidity).

Aggregation (`aggregate()`):

  - `aggregate_liquidity_score = min(legs)`  ← weakest link
  - `aggregate_fill_confidence = min(legs)`  ← weakest link
  - `suggested_order_type` = LIMIT if every leg ≥ 0.70 else MARKETABLE_LIMIT
  - `notes` = collected `size_warnings` plus the M1.12 downgrade hint
    when `aggregate_fill_confidence < 0.50`

Composer bridge (`liquidity_penalty()`):

  Maps `Execution → illiquidity_penalty ∈ [0, 1]` for the Confidence
  Composer (`engine.confidence.compose`):

      illiquidity_penalty = clip01(1.0 − aggregate_fill_confidence)

  The composer applies the `weights.penalty_caps.liquidity` (default
  0.25) multiplicatively.

Empty-leg case (REDUCE_COVERAGE, MONETIZE_PUT, NO_OP from the M1.9
Recommendation Engine produce no new legs): `assess([])` returns an
`Execution` with aggregate scores of 1.0 (trivially fillable), LIMIT
order type, no legs, no notes. Downstream `liquidity_penalty()` is 0.0
for an empty Execution — these emit codes don't pay an illiquidity
penalty in the Confidence Composer.
"""

from __future__ import annotations

from collections.abc import Sequence

from engine._utils import clip01
from engine.execution.fill import (
    _LIMIT_THRESHOLD,
    DOWNGRADE_THRESHOLD,
    fill_confidence,
    suggested_order_type,
)
from engine.execution.liquidity import compute_spread_bps, liquidity_score
from engine.execution.size import limit_price_band, size_warnings
from engine.execution.slippage import expected_slippage
from engine.execution.types import Execution, ExecutionLeg, OrderType
from engine.strike_selector.types import StrikeLeg


def assess(
    *,
    legs: Sequence[StrikeLeg],
    quantities: Sequence[int] | None = None,
) -> Execution:
    """V1 Execution Feasibility orchestrator per plan §9.8.

    Args:
        legs:        Concrete `StrikeLeg`s from the M1.7 Strike
                     Selector. Empty tuple is valid (REDUCE_COVERAGE,
                     MONETIZE_PUT, NO_OP).
        quantities:  Per-leg contract counts (signed for symmetry with
                     `StrikeLeg.side`; absolute value is used for the
                     size math). Defaults to `[1] * len(legs)` —
                     suitable for the V1 "1 contract per leg" calibration
                     fixtures. The Master Decision Engine (M1.13) will
                     pass real counts derived from
                     `Action.parameters['size_pct'] × underlying_shares / 100`.

    Returns:
        `Execution` with per-leg + aggregate scoring. Pure function
        (per ADR-0005): same inputs → byte-identical output.

    Raises:
        ValueError: When `quantities` is provided and `len(quantities)`
            doesn't match `len(legs)`.
    """
    if quantities is None:
        quantities_resolved: tuple[int, ...] = tuple(1 for _ in legs)
    else:
        if len(quantities) != len(legs):
            raise ValueError(
                f"assess: len(quantities)={len(quantities)} doesn't match "
                f"len(legs)={len(legs)}"
            )
        quantities_resolved = tuple(int(q) for q in quantities)

    exec_legs: list[ExecutionLeg] = []
    # noqa B905: pair-wise iteration with explicit length check above —
    # strict=True is the 3.10+ form, dropped here for the 3.9 sandbox shim.
    for leg, qty in zip(legs, quantities_resolved):  # noqa: B905
        exec_legs.append(_assess_one_leg(leg, qty))

    agg_liq, agg_fill, agg_order, notes = aggregate(tuple(exec_legs))

    return Execution(
        aggregate_liquidity_score=agg_liq,
        aggregate_fill_confidence=agg_fill,
        suggested_order_type=agg_order,
        legs=tuple(exec_legs),
        notes=notes,
    )


def aggregate(
    legs: Sequence[ExecutionLeg],
) -> tuple[float, float, OrderType, tuple[str, ...]]:
    """Reduce per-leg results into top-level summary fields.

    Empty legs → `(1.0, 1.0, LIMIT, ())`. The Confidence Composer's
    `illiquidity_penalty` is then `clip01(1.0 − 1.0) = 0.0` — no
    penalty for the no-new-leg emit codes (REDUCE_COVERAGE etc.).

    Non-empty legs:
      - `agg_liq`  = `min(leg.liquidity_score)`
      - `agg_fill` = `min(leg.fill_confidence)`
      - `order_type` = LIMIT iff every leg fill ≥ `_LIMIT_THRESHOLD` (0.70)
      - `notes` = collected per-leg `size_warnings` + downgrade hint
        when `agg_fill < DOWNGRADE_THRESHOLD` (0.50).
    """
    if not legs:
        return 1.0, 1.0, OrderType.LIMIT, ()

    agg_liq = min(leg.liquidity_score for leg in legs)
    agg_fill = min(leg.fill_confidence for leg in legs)

    every_leg_passes_limit = all(
        leg.fill_confidence >= _LIMIT_THRESHOLD for leg in legs
    )
    order_type = OrderType.LIMIT if every_leg_passes_limit else OrderType.MARKETABLE_LIMIT

    notes_list: list[str] = []
    for leg in legs:
        notes_list.extend(leg.size_warnings)
    if agg_fill < DOWNGRADE_THRESHOLD:
        notes_list.append(
            f"aggregate fill confidence {agg_fill:.2f} below {DOWNGRADE_THRESHOLD:.2f} "
            "— downgrade callback recommended (re-run Strike Selector with "
            "adjusted filters, M1.12)"
        )

    return agg_liq, agg_fill, order_type, tuple(notes_list)


def liquidity_penalty(execution: Execution) -> float:
    """Composer bridge — map `Execution → illiquidity_penalty ∈ [0, 1]`.

    V1 mapping: `clip01(1.0 − aggregate_fill_confidence)`. The
    Confidence Composer applies the configured liquidity cap (default
    0.25 per `packages/engine/config/weights.yaml`) multiplicatively.

    Plug into `recommend(illiquidity_penalty=...)` or pass to
    `engine.confidence.compute_confidence_inputs(...)`.

    Pure function (per ADR-0005).
    """
    return clip01(1.0 - execution.aggregate_fill_confidence)


# ----------------------------------------------------------------------
# Internals
# ----------------------------------------------------------------------


def _assess_one_leg(leg: StrikeLeg, qty: int) -> ExecutionLeg:
    """Per-leg pipeline. Defensive against missing quote fields."""
    c = leg.contract
    bid = c.bid
    ask = c.ask
    mid = c.mid
    oi = c.open_interest if c.open_interest is not None else 0
    volume = c.volume if c.volume is not None else 0

    spread_bps_val = compute_spread_bps(bid=bid, ask=ask, mid=mid)
    liq = liquidity_score(oi=oi, volume=volume, spread_bps=spread_bps_val)
    slip = expected_slippage(bid=bid, ask=ask, oi=oi, qty=qty)
    fill_conf = fill_confidence(liquidity=liq, spread_bps=spread_bps_val)
    band = limit_price_band(bid=bid, ask=ask, mid=mid)
    warnings = size_warnings(oi=oi, volume=volume, qty=qty)

    return ExecutionLeg(
        leg_id=_leg_id(leg),
        liquidity_score=liq,
        spread_bps=spread_bps_val,
        fill_confidence=fill_conf,
        expected_slippage=slip,
        suggested_order_type=suggested_order_type(fill_conf),
        limit_price_band=band,
        size_warnings=warnings,
    )


def _leg_id(leg: StrikeLeg) -> str:
    """Stable human-readable identifier built from (side, type, strike, expiry).

    Example: `"short_call_415.0_2026-05-16"`. Format is informational
    only — downstream code should not parse it (use the fields on the
    `OptionContract` directly).
    """
    c = leg.contract
    side_str = leg.side.value.lower()
    type_str = c.option_type.value.lower()
    return f"{side_str}_{type_str}_{c.strike}_{c.expiry.isoformat()}"
