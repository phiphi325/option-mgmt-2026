"""Public entry point for the Collar Builder engine.

`build()` is the single function the M1.16a standalone endpoint and
M1.11b's Master Decision integration both call. It performs input
validation, derives sensible defaults from the user's profile, and
dispatches to the three intent solvers in `structures.py`.

Per master plan §9.10 and M1.11a dev spec
(`docs/phased-design/phase-1/m1.11a-collar-builder-engine.md`).
"""

from __future__ import annotations

from engine.confidence import DEFAULT_WEIGHTS
from engine.confidence.types import Weights
from engine.flow_score.types import FlowScore
from engine.market_state.classify import MarketStateResult
from engine.profiles import UserStrategyProfile
from engine.types import ChainSnapshot

from .structures import (
    _candidate_expirations,
    solve_defensive,
    solve_income,
    solve_zero_cost,
)
from .types import CollarIntent, CollarStructure

# Default horizon when the caller doesn't provide one. The profile's
# `dte_band_days` isn't exposed in V1; use a sane default per master
# plan §9.10 default of "profile.dte_band_days[1]" ≈ 45.
DEFAULT_HORIZON_DAYS = 45

# Each option contract covers 100 shares.
SHARES_PER_CONTRACT = 100


def build(
    *,
    spot: float,
    underlying_qty: int,
    chain: ChainSnapshot,
    profile: UserStrategyProfile,
    market_state: MarketStateResult,
    flow_score: FlowScore,
    intents: list[CollarIntent] | None = None,
    horizon_days: int | None = None,
    coverage_ratio: float | None = None,
    weights: Weights | None = None,
) -> list[CollarStructure]:
    """Build ranked collar candidates per master plan §9.10.

    Args:
        spot: Underlying spot price (matches `chain.spot`).
        underlying_qty: Number of shares the user holds. Must be ≥ 100.
        chain: The current option-chain snapshot. `chain.as_of` is used
            to derive days-to-expiry for each candidate.
        profile: User Strategy Profile. `drawdown_tolerance` drives the
            put-strike floor; `max_coverage_pct` drives the default
            `coverage_ratio`.
        market_state: M1.4 classification — drives regime + signal
            heuristics for the Confidence Composer.
        flow_score: M1.5 flow score — drives the flow-alignment input.
        intents: Which intents to solve for. Defaults to all three.
            Order in the input is the order in the output.
        horizon_days: Max DTE to consider. Defaults to
            `DEFAULT_HORIZON_DAYS` (45).
        coverage_ratio: Fraction of position to cover. Defaults to
            `profile.max_coverage_pct`. Must be in (0, 1].
        weights: M1.10 weights for Confidence composition. Defaults to
            `DEFAULT_WEIGHTS` (v2.0).

    Returns:
        A list of `CollarStructure` candidates, one per requested
        intent that had a feasible solution. The list is intent-
        ordered (aligned with the input `intents` list); intents with
        no feasible structure are skipped (length of output ≤ length
        of input).

    Raises:
        ValueError if `underlying_qty < 100` (cannot collar fewer than
            100 shares).
        ValueError if the resolved `coverage_ratio * underlying_qty <
            SHARES_PER_CONTRACT` (would require 0 contracts).
        ValueError if `horizon_days ≤ 0`.
        ValueError if `coverage_ratio ≤ 0` or `> 1`.
    """
    if underlying_qty < SHARES_PER_CONTRACT:
        raise ValueError(
            f"underlying_qty must be >= {SHARES_PER_CONTRACT} "
            f"(cannot collar fewer than {SHARES_PER_CONTRACT} shares); "
            f"got {underlying_qty}"
        )

    resolved_intents = intents if intents is not None else list(CollarIntent)
    resolved_horizon = horizon_days if horizon_days is not None else DEFAULT_HORIZON_DAYS
    resolved_coverage = (
        coverage_ratio if coverage_ratio is not None else profile.max_coverage_pct
    )
    resolved_weights = weights if weights is not None else DEFAULT_WEIGHTS

    if resolved_horizon <= 0:
        raise ValueError(f"horizon_days must be positive; got {resolved_horizon}")
    if not (0.0 < resolved_coverage <= 1.0):
        raise ValueError(
            f"coverage_ratio must be in (0, 1]; got {resolved_coverage}"
        )

    contracts = int((underlying_qty * resolved_coverage) // SHARES_PER_CONTRACT)
    if contracts < 1:
        raise ValueError(
            f"coverage_ratio {resolved_coverage} * underlying_qty {underlying_qty} "
            f"resolves to {contracts} contracts; need at least 1 "
            f"({SHARES_PER_CONTRACT} shares)"
        )

    if not resolved_intents:
        return []

    expirations = _candidate_expirations(chain, resolved_horizon)
    if not expirations:
        return []

    results: list[CollarStructure] = []
    for intent in resolved_intents:
        result: CollarStructure | None
        if intent is CollarIntent.ZERO_COST:
            result = solve_zero_cost(
                spot=spot,
                chain=chain,
                contracts=contracts,
                profile=profile,
                market_state=market_state,
                flow_score=flow_score,
                expirations=expirations,
                weights=resolved_weights,
            )
        elif intent is CollarIntent.INCOME:
            result = solve_income(
                spot=spot,
                chain=chain,
                contracts=contracts,
                profile=profile,
                market_state=market_state,
                flow_score=flow_score,
                expirations=expirations,
                weights=resolved_weights,
            )
        elif intent is CollarIntent.DEFENSIVE:
            result = solve_defensive(
                spot=spot,
                chain=chain,
                contracts=contracts,
                profile=profile,
                market_state=market_state,
                flow_score=flow_score,
                expirations=expirations,
                weights=resolved_weights,
            )
        else:
            # Unreachable for the StrEnum, but mypy requires the branch.
            continue
        if result is not None:
            results.append(result)
    return results
