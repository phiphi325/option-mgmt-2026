"""Strike Selector — `select_strikes()` orchestrator.

Per plan v1.2 §9.5 (Strike Selector) and §17 M1.8.

`select_strikes()` consumes a `Recommendation` + `ChainSnapshot` and
returns a `StrikeSelection`: zero or more `StrikeLeg`s with the
selected `OptionContract`s and the match diagnostics.

## Algorithm (per required leg)

  1. Filter contracts by `option_type` (call or put — depending on the
     leg) and to those with valid liquidity:
       - `iv is not None and iv > 0` (need IV for BS delta)
       - `open_interest > 0`
       - `bid is not None and ask is not None and ask >= bid >= 0`
  2. Group surviving contracts by expiry and pick the expiry whose
     DTE is closest to `target_dte`. Tie-break by smaller DTE (the
     closer-dated leg is the more liquid one in practice).
  3. Within the selected expiry, compute BS delta (using
     `engine.greeks.delta`) for each contract using the contract's own
     IV. Pick the strike whose `|delta_actual − delta_target|` is
     smallest. Tie-break by lower strike for determinism.
  4. Wrap the selected contract in a `StrikeLeg` with the diagnostics.

If any step yields no eligible contract, `select_strikes()` returns a
`StrikeSelection` with `legs=()` and a human-readable
`skipped_reason`.

## V1 constants

Two heuristics live here:

  - `_DTE_MIN_DAYS`: 7. Contracts expiring within a week are excluded
    because BS Greeks become unstable and gamma risk dominates.
  - `_DTE_MAX_DAYS`: 365. Far-dated LEAPS are excluded because their
    flow signals are noisy and bid/ask spreads are wide. The §9.5
    spec leaves both bounds as in-engine constants for V1; ADR-0008
    plans to move them to `rules.yaml` in Phase 1.5.

Pure function per ADR-0005 — no I/O, no DB, no clock, no env.
"""

from __future__ import annotations

from collections.abc import Sequence

from engine.greeks import delta
from engine.recommendation.types import Recommendation, StrategyClass
from engine.strike_selector.types import LegSide, StrikeLeg, StrikeSelection
from engine.types import ChainSnapshot, OptionContract, OptionType

# V1 priors per §9.5. Live in-engine in V1; Phase 1.5 rules.yaml hot-swap.
_DTE_MIN_DAYS: int = 7
_DTE_MAX_DAYS: int = 365


# ----------------------------------------------------------------------
# Leg structure per strategy class
# ----------------------------------------------------------------------
#
# Each strategy expands to one or more (OptionType, LegSide, target_sign)
# tuples. `target_sign` is +1 for calls and -1 for puts — applied to the
# `target_delta` from the Recommendation's parameters dict.

_LegSpec = tuple[OptionType, LegSide, int]

_LEGS_BY_STRATEGY: dict[StrategyClass, tuple[_LegSpec, ...]] = {
    StrategyClass.COVERED_CALL_AGGRESSIVE: (
        (OptionType.CALL, LegSide.SHORT, +1),
    ),
    StrategyClass.COVERED_CALL_PARTIAL: (
        (OptionType.CALL, LegSide.SHORT, +1),
    ),
    StrategyClass.PROTECTIVE_PUT: (
        (OptionType.PUT, LegSide.LONG, -1),
    ),
    StrategyClass.COLLAR: (
        (OptionType.CALL, LegSide.SHORT, +1),
        (OptionType.PUT, LegSide.LONG, -1),
    ),
    # REDUCE_CALL_COVERAGE has no new-leg structure in V1 — it requires
    # the user's existing position to identify which short call to
    # close. The API layer handles that lookup.
    StrategyClass.REDUCE_CALL_COVERAGE: (),
    StrategyClass.WAIT: (),
    StrategyClass.MONITOR: (),
}


def _eligible_contracts(
    *,
    contracts: Sequence[OptionContract],
    option_type: OptionType,
) -> list[OptionContract]:
    """Filter to liquid contracts of the requested option type."""
    out: list[OptionContract] = []
    for c in contracts:
        if c.option_type is not option_type:
            continue
        if c.iv is None or c.iv <= 0.0:
            continue
        if c.open_interest <= 0:
            continue
        if c.bid is None or c.ask is None:
            continue
        if c.ask < c.bid or c.bid < 0.0:
            continue
        out.append(c)
    return out


def _dte_days(as_of_to_expiry_days: int) -> int:
    """Wrap the day-count in a function for one-place tweaking later."""
    return as_of_to_expiry_days


def _pick_expiry(
    *,
    eligible: Sequence[OptionContract],
    as_of_year_day: dict[OptionContract, int],
    target_dte: float,
) -> int | None:
    """Pick the DTE (integer) whose absolute distance to target_dte
    is smallest, tie-breaking by smaller DTE for determinism. Filters
    out DTEs outside `[_DTE_MIN_DAYS, _DTE_MAX_DAYS]`.

    `as_of_year_day` is a per-contract DTE map precomputed by the
    caller; it avoids recomputing for each ranking pass.

    Returns the chosen DTE, or `None` if no eligible expiry remains.
    """
    distinct_dtes: set[int] = set()
    for c in eligible:
        d = as_of_year_day[c]
        if _DTE_MIN_DAYS <= d <= _DTE_MAX_DAYS:
            distinct_dtes.add(d)

    if not distinct_dtes:
        return None

    # min by (|dte − target_dte|, dte) — ascending; lower dte wins ties
    return min(distinct_dtes, key=lambda d: (abs(d - target_dte), d))


def _delta_for_contract(
    *,
    contract: OptionContract,
    spot: float,
    tau: float,
    risk_free_rate: float,
    dividend_yield: float,
) -> float:
    """Compute BS delta for the contract using the contract's own IV.

    The caller ensures `contract.iv is not None and contract.iv > 0`
    via `_eligible_contracts`; the assert is a static-checker hint.
    """
    assert contract.iv is not None and contract.iv > 0.0  # noqa: S101
    return delta(
        spot=spot,
        strike=contract.strike,
        tau=tau,
        iv=contract.iv,
        r=risk_free_rate,
        q=dividend_yield,
        option_type=contract.option_type,
    )


def _midprice(*, contract: OptionContract) -> float | None:
    """Return the mid price for the contract.

    Uses `contract.mid` if non-None, else `(bid + ask) / 2` when both
    sides of the quote are present, else `None`.
    """
    if contract.mid is not None:
        return contract.mid
    if contract.bid is not None and contract.ask is not None:
        return (contract.bid + contract.ask) / 2.0
    return None


def _select_one_leg(
    *,
    contracts: Sequence[OptionContract],
    option_type: OptionType,
    side: LegSide,
    target_dte: float,
    target_delta_unsigned: float,
    target_sign: int,
    spot: float,
    as_of_year_day: dict[OptionContract, int],
    risk_free_rate: float,
    dividend_yield: float,
) -> tuple[StrikeLeg | None, str | None]:
    """Pick one leg or explain why none was selectable.

    Returns:
        (leg, None) on success; (None, reason) on failure.
    """
    eligible = _eligible_contracts(contracts=contracts, option_type=option_type)
    if not eligible:
        return None, (
            f"No eligible {option_type.value} contracts in chain "
            f"(filtered by IV/OI/quote)"
        )

    chosen_dte = _pick_expiry(
        eligible=eligible,
        as_of_year_day=as_of_year_day,
        target_dte=target_dte,
    )
    if chosen_dte is None:
        return None, (
            f"No {option_type.value} expiry within DTE band "
            f"[{_DTE_MIN_DAYS}, {_DTE_MAX_DAYS}]"
        )

    # Restrict to the chosen DTE
    at_dte = [c for c in eligible if as_of_year_day[c] == chosen_dte]
    if not at_dte:  # pragma: no cover  (the chosen DTE came from these)
        return None, "Internal error: chosen DTE no longer in eligible set"

    # Signed target for matching (call → +0.25, put → -0.25)
    target_delta_signed = target_sign * target_delta_unsigned

    # Tau for BS delta — use the chosen DTE as days / 365
    tau = chosen_dte / 365.0

    # Score every contract at the chosen DTE and pick the closest match.
    # We materialize tuples eagerly inside the function body to avoid the
    # B023 closure-over-loop-variable footgun (M1.6 lesson).
    scored = [
        (
            abs(
                _delta_for_contract(
                    contract=c,
                    spot=spot,
                    tau=tau,
                    risk_free_rate=risk_free_rate,
                    dividend_yield=dividend_yield,
                )
                - target_delta_signed
            ),
            c.strike,
            c,
        )
        for c in at_dte
    ]
    # Tie-break by lower strike — matches the M1.6 skew_25d convention.
    _, _, chosen = min(scored, key=lambda t: (t[0], t[1]))

    actual_delta = _delta_for_contract(
        contract=chosen,
        spot=spot,
        tau=tau,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
    )

    leg = StrikeLeg(
        contract=chosen,
        side=side,
        delta_target=target_delta_signed,
        delta_actual=actual_delta,
        delta_distance=abs(actual_delta - target_delta_signed),
        dte_actual=chosen_dte,
        mid_price=_midprice(contract=chosen),
    )
    return leg, None


def select_strikes(
    *,
    recommendation: Recommendation,
    chain_snapshot: ChainSnapshot,
    risk_free_rate: float = 0.05,
    dividend_yield: float = 0.0,
) -> StrikeSelection:
    """V1 Strike Selector entry point.

    Args:
        recommendation: Output from `engine.recommendation.recommend()`.
            Reads `strategy_class` and `parameters` (`target_dte`,
            `target_delta`).
        chain_snapshot: Frozen option-chain projection. Carries spot,
            as_of, and contracts.
        risk_free_rate: Continuous-compounding risk-free rate. Default
            `0.05` (matches the M1.6 `skew_25d` V1 prior).
        dividend_yield: Continuous-compounding dividend yield. Default
            `0.0` (sensible for MSFT-class names).

    Returns:
        `StrikeSelection` with zero or more `StrikeLeg`s.

    Raises:
        ValueError: When `chain_snapshot.spot <= 0` (defensive). Other
            invalid inputs (empty chain, no eligible contracts) flow
            through as `legs=()` + `skipped_reason`.

    The function is pure (per ADR-0005). For strategy classes that
    require no concrete legs in V1 (`WAIT`, `MONITOR`,
    `REDUCE_CALL_COVERAGE`), the result has `legs=()` and a
    `skipped_reason` documenting why.
    """
    if chain_snapshot.spot <= 0.0:
        raise ValueError(
            f"select_strikes: chain_snapshot.spot must be > 0; got {chain_snapshot.spot}"
        )

    strategy = recommendation.strategy_class
    leg_specs = _LEGS_BY_STRATEGY[strategy]

    if not leg_specs:
        return StrikeSelection(
            strategy_class=strategy,
            legs=(),
            skipped_reason=(
                f"{strategy.value} requires no concrete strike selection "
                f"(WAIT/MONITOR/REDUCE_CALL_COVERAGE)"
            ),
        )

    params = recommendation.parameters
    target_dte = params.get("target_dte")
    target_delta_unsigned = params.get("target_delta")
    if target_dte is None or target_delta_unsigned is None:
        return StrikeSelection(
            strategy_class=strategy,
            legs=(),
            skipped_reason=(
                f"Recommendation.parameters missing target_dte or "
                f"target_delta for {strategy.value}"
            ),
        )

    # Precompute per-contract DTE so we don't recompute it for every
    # ranking pass per leg. Use the M1.6 365-day convention.
    as_of = chain_snapshot.as_of
    as_of_year_day: dict[OptionContract, int] = {
        c: _dte_days((c.expiry - as_of).days) for c in chain_snapshot.contracts
    }

    selected_legs: list[StrikeLeg] = []
    for option_type, side, target_sign in leg_specs:
        leg, reason = _select_one_leg(
            contracts=chain_snapshot.contracts,
            option_type=option_type,
            side=side,
            target_dte=target_dte,
            target_delta_unsigned=target_delta_unsigned,
            target_sign=target_sign,
            spot=chain_snapshot.spot,
            as_of_year_day=as_of_year_day,
            risk_free_rate=risk_free_rate,
            dividend_yield=dividend_yield,
        )
        if leg is None:
            return StrikeSelection(
                strategy_class=strategy,
                legs=(),
                skipped_reason=reason,
            )
        selected_legs.append(leg)

    return StrikeSelection(
        strategy_class=strategy,
        legs=tuple(selected_legs),
        skipped_reason=None,
    )


# Exported constants for downstream introspection / tests.
DTE_MIN_DAYS: int = _DTE_MIN_DAYS
DTE_MAX_DAYS: int = _DTE_MAX_DAYS
