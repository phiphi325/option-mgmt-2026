"""Execution downgrade callback (M1.12).

Per plan v1.2 §9.8 (last paragraph) and §17 M1.12.

> "if any leg has `fill_confidence < 0.5`, the Recommendation Engine
>  receives a callback to propose nearby strikes with better liquidity
>  (re-runs Strike Selector with adjusted filters)."

The M1.11 Execution Feasibility Module flags weak fills via per-leg
`fill_confidence` and via the aggregate `DOWNGRADE_THRESHOLD = 0.50`
trigger. M1.12 is the call-site that acts on that signal:

  1. Call `select_strikes()` + `assess()` once with the user's
     original `Action`.
  2. If every leg's `fill_confidence ≥ threshold`, return the
     original selection unchanged.
  3. Otherwise, walk a V1 escalation ladder — successively stricter
     liquidity-floor filters applied to the `ChainSnapshot` — and
     re-run `select_strikes()` until either all legs pass OR the
     ladder is exhausted.
  4. Return a `DowngradeResult` carrying both the original and the
     final selection / execution, plus an `escalated` flag and a
     human-readable `downgrade_notes` audit trail.

`escalated=True` means the chain is genuinely too illiquid for the
requested action at any liquidity-floor level the V1 ladder explores.
The Master Decision Engine (M1.13) reads this signal and decides
whether to downgrade the rule outcome to `NO_OP` or just pass the
weaker fill through with the higher M1.10 illiquidity penalty.

Why pre-filter the chain rather than adding kwargs to `select_strikes()`?
ADR-0005 prefers small, focused contracts: `select_strikes()` does
delta + DTE matching against eligible contracts; M1.12 decides what
"eligible" means at each ladder rung. The downgrade module owns the
ladder logic; the Strike Selector stays clean.

Pure function per ADR-0005 — no I/O, no clock, no env.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from engine.execution.assess import assess
from engine.execution.fill import DOWNGRADE_THRESHOLD
from engine.execution.liquidity import compute_spread_bps
from engine.execution.types import Execution
from engine.recommendation.types import Action
from engine.strike_selector.select import select_strikes
from engine.strike_selector.types import StrikeSelection
from engine.types import ChainSnapshot, OptionContract

# ----------------------------------------------------------------------
# V1 downgrade ladder
# ----------------------------------------------------------------------
#
# Each rung is a (min_oi, min_volume, max_spread_bps) tuple — the
# liquidity floor `ChainSnapshot.contracts` must clear to be passed
# into the re-run `select_strikes()`. Rungs are ordered from least to
# most stringent. The Strike Selector's existing eligibility check
# (`iv > 0`, `oi > 0`, valid bid/ask) still applies on top.
#
# V1 priors chosen against the §22.13 worked-example calibration:
#   - rung 1: 500 OI + 50 vol + 200 bps spread — typical MSFT weekly
#     ATM strikes clear this; far-OTM may not.
#   - rung 2: 2000 OI + 100 vol + 100 bps spread — even tighter; only
#     the most active strikes clear it.
#
# Phase 4 ML may learn rung definitions; the (min_oi, min_volume,
# max_spread_bps) shape is the replaceable contract.

_LiquidityFloor = tuple[int, int, int]

_DOWNGRADE_LADDER: tuple[_LiquidityFloor, ...] = (
    (500, 50, 200),
    (2000, 100, 100),
)


# ----------------------------------------------------------------------
# Public types
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class DowngradeResult:
    """Result of `downgrade_if_needed()`.

    Fields:
        original_selection:  `StrikeSelection` from the first
                             `select_strikes()` call (no liquidity
                             filter). Used by the UI to show "what
                             the rule wanted before downgrade".
        original_execution:  Per-leg `Execution` for the original
                             selection.
        final_selection:     `StrikeSelection` after the (possibly
                             empty) downgrade ladder. Equals
                             `original_selection` when no downgrade
                             was needed.
        final_execution:     Per-leg `Execution` for the final
                             selection.
        iterations:          0 if no retry was needed; 1 if the first
                             ladder rung succeeded; etc. Max value is
                             `len(_DOWNGRADE_LADDER)`.
        escalated:           `True` when the final execution still
                             fails the threshold — the ladder couldn't
                             rescue the action and downstream should
                             consider an even more conservative
                             downgrade (e.g. NO_OP).
        downgrade_notes:     Human-readable audit trail. Empty when no
                             retry happened; otherwise lists the
                             ladder rungs attempted with outcomes.

    Frozen dataclass per ADR-0005.
    """

    original_selection: StrikeSelection
    original_execution: Execution
    final_selection: StrikeSelection
    final_execution: Execution
    iterations: int
    escalated: bool
    downgrade_notes: tuple[str, ...] = field(default_factory=tuple)


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------


def downgrade_if_needed(
    *,
    action: Action,
    chain_snapshot: ChainSnapshot,
    risk_free_rate: float = 0.05,
    dividend_yield: float = 0.0,
    threshold: float = DOWNGRADE_THRESHOLD,
    quantities: Sequence[int] | None = None,
) -> DowngradeResult:
    """V1 Execution downgrade callback per plan §9.8 + §17 M1.12.

    Pipeline:

      1. `select_strikes(action, chain_snapshot)` → original selection.
      2. `assess(selection.legs)` → original execution.
      3. If every leg in the original execution has
         `fill_confidence ≥ threshold`, return immediately (iterations=0,
         escalated=False).
      4. Otherwise iterate the V1 ladder, pre-filtering the chain by
         (min_oi, min_volume, max_spread_bps) at each rung and re-calling
         `select_strikes()`. Stop at the first rung where every leg
         passes the threshold.
      5. If no rung passes, return the last attempted result with
         `escalated=True`.

    Empty original selections (REDUCE_COVERAGE, MONETIZE_PUT, NO_OP)
    bypass the ladder — there's no concrete leg to relocate. The
    return carries `original_execution.legs == ()` and the implicit
    "trivially fillable" `aggregate_*=1.0` semantics from `assess([])`.

    Args:
        action:           The user's `Action` from `RecommendationResult.actions`.
        chain_snapshot:   Frozen `ChainSnapshot`.
        risk_free_rate:   BS pricing input. Passthrough to `select_strikes()`.
        dividend_yield:   BS pricing input. Passthrough to `select_strikes()`.
        threshold:        Per-leg `fill_confidence` floor. Default is
                          `DOWNGRADE_THRESHOLD = 0.50` per §9.8.
        quantities:       Per-leg contract counts. Defaults to `[1]*N`.
                          Must match `len(selection.legs)` at every
                          ladder rung (the rung is rejected with a note
                          if a different leg count emerges).

    Returns:
        `DowngradeResult`. Pure function (per ADR-0005): same inputs →
        byte-identical output.
    """
    original_selection = select_strikes(
        action=action,
        chain_snapshot=chain_snapshot,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
    )
    original_execution = _assess_with_default_qty(
        original_selection, quantities=quantities
    )

    # Empty selections never trigger a downgrade — there's nothing to relocate.
    if not original_selection.legs:
        return DowngradeResult(
            original_selection=original_selection,
            original_execution=original_execution,
            final_selection=original_selection,
            final_execution=original_execution,
            iterations=0,
            escalated=False,
            downgrade_notes=(),
        )

    if _all_legs_pass(original_execution, threshold):
        return DowngradeResult(
            original_selection=original_selection,
            original_execution=original_execution,
            final_selection=original_selection,
            final_execution=original_execution,
            iterations=0,
            escalated=False,
            downgrade_notes=(),
        )

    notes: list[str] = [
        f"original fill_confidence min={_min_fill(original_execution):.2f} "
        f"< threshold={threshold:.2f}; entering ladder"
    ]
    best_selection = original_selection
    best_execution = original_execution

    for rung_idx, floor in enumerate(_DOWNGRADE_LADDER, start=1):
        min_oi, min_volume, max_spread_bps = floor
        filtered = filter_chain_by_liquidity(
            chain_snapshot,
            min_oi=min_oi,
            min_volume=min_volume,
            max_spread_bps=max_spread_bps,
        )
        rung_label = (
            f"rung {rung_idx} (min_oi={min_oi}, min_volume={min_volume}, "
            f"max_spread_bps={max_spread_bps})"
        )

        if not filtered.contracts:
            notes.append(f"{rung_label}: no contracts cleared the floor; skip")
            continue

        rung_selection = select_strikes(
            action=action,
            chain_snapshot=filtered,
            risk_free_rate=risk_free_rate,
            dividend_yield=dividend_yield,
        )

        # If the rung lost a leg (e.g. collar's put leg has no liquid
        # candidate at this floor), skip the rung — the result would be
        # worse than the original.
        if len(rung_selection.legs) != len(original_selection.legs):
            notes.append(
                f"{rung_label}: leg count {len(rung_selection.legs)} != "
                f"original {len(original_selection.legs)}; skip"
            )
            continue

        rung_execution = _assess_with_default_qty(
            rung_selection, quantities=quantities
        )
        rung_min = _min_fill(rung_execution)

        if _all_legs_pass(rung_execution, threshold):
            notes.append(
                f"{rung_label}: SUCCESS, all legs fill >= {threshold:.2f} "
                f"(min={rung_min:.2f})"
            )
            return DowngradeResult(
                original_selection=original_selection,
                original_execution=original_execution,
                final_selection=rung_selection,
                final_execution=rung_execution,
                iterations=rung_idx,
                escalated=False,
                downgrade_notes=tuple(notes),
            )

        # Rung didn't fully pass; keep the best-so-far if it improved.
        if rung_min > _min_fill(best_execution):
            notes.append(
                f"{rung_label}: partial improvement to min_fill={rung_min:.2f}; "
                "keeping as best-so-far"
            )
            best_selection = rung_selection
            best_execution = rung_execution
        else:
            notes.append(
                f"{rung_label}: no improvement (min_fill={rung_min:.2f}); skip"
            )

    notes.append(
        f"escalated: ladder exhausted; final min_fill={_min_fill(best_execution):.2f} "
        f"still < threshold={threshold:.2f}"
    )
    return DowngradeResult(
        original_selection=original_selection,
        original_execution=original_execution,
        final_selection=best_selection,
        final_execution=best_execution,
        iterations=len(_DOWNGRADE_LADDER),
        escalated=True,
        downgrade_notes=tuple(notes),
    )


def filter_chain_by_liquidity(
    chain_snapshot: ChainSnapshot,
    *,
    min_oi: int = 0,
    min_volume: int = 0,
    max_spread_bps: int | None = None,
) -> ChainSnapshot:
    """Return a new `ChainSnapshot` keeping only contracts that clear the floor.

    A contract is kept iff:
      - `open_interest ≥ min_oi`
      - `volume ≥ min_volume`
      - `max_spread_bps is None` OR `compute_spread_bps(bid, ask, mid) ≤ max_spread_bps`

    Contracts with broken quotes (`compute_spread_bps` returns the 9999
    sentinel) are excluded whenever `max_spread_bps is not None`.

    Pure function (per ADR-0005). The returned `ChainSnapshot` reuses
    the original's `underlying`, `spot`, and `as_of`.
    """
    kept: list[OptionContract] = []
    for c in chain_snapshot.contracts:
        if c.open_interest < min_oi:
            continue
        if c.volume < min_volume:
            continue
        if max_spread_bps is not None:
            bps = compute_spread_bps(bid=c.bid, ask=c.ask, mid=c.mid)
            if bps > max_spread_bps:
                continue
        kept.append(c)
    return ChainSnapshot(
        underlying=chain_snapshot.underlying,
        spot=chain_snapshot.spot,
        as_of=chain_snapshot.as_of,
        contracts=tuple(kept),
    )


# ----------------------------------------------------------------------
# Internals
# ----------------------------------------------------------------------


def _all_legs_pass(execution: Execution, threshold: float) -> bool:
    """True iff every leg in `execution.legs` has `fill_confidence ≥ threshold`.

    An empty `legs` tuple returns True (no leg violates the floor).
    """
    return all(leg.fill_confidence >= threshold for leg in execution.legs)


def _min_fill(execution: Execution) -> float:
    """Minimum per-leg `fill_confidence`; `1.0` when there are no legs.

    Mirrors the aggregate-fill semantics in `engine.execution.assess.aggregate`:
    empty legs are trivially fillable.
    """
    if not execution.legs:
        return 1.0
    return min(leg.fill_confidence for leg in execution.legs)


def _assess_with_default_qty(
    selection: StrikeSelection,
    *,
    quantities: Sequence[int] | None,
) -> Execution:
    """Call `assess()` with quantities defaulting to `[1] * len(legs)`."""
    if quantities is None or len(quantities) != len(selection.legs):
        quantities = tuple(1 for _ in selection.legs)
    return assess(legs=selection.legs, quantities=quantities)
