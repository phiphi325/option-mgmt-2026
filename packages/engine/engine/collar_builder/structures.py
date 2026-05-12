"""Per-intent collar solvers + structure assembly.

Three solvers, one per `CollarIntent` (zero_cost / income / defensive).
Each solver does a bounded grid search over (K_put × K_call) and returns
the best candidate per the intent's objective function, or `None` when
no candidate passes liquidity + profile constraints.

Algorithm (per master plan §9.10):

  1. Filter chain to candidate expirations within `[0, horizon_days]`.
  2. For each candidate expiration:
     a. Calls: filter to K_call > spot AND short-call delta in band.
     b. Puts:  filter to K_put < spot AND `protected_downside_pct`
        satisfies the intent's minimum.
  3. Grid-evaluate each (K_put, K_call) pair → score per intent.
  4. Filter out pairs that fail M1.11 Execution Feasibility floors.
  5. Return the best (highest-scoring) candidate, or None.

The solvers don't compute deltas themselves — they accept an optional
explicit delta on each `OptionContract` and fall back to a moneyness
proxy when absent. The proxy is monotone (so delta-banding still
ranks correctly) but is not Black-Scholes-accurate.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from engine.confidence import compose
from engine.confidence.types import ConfidenceInputs, Weights
from engine.execution.assess import assess
from engine.execution.types import Execution
from engine.flow_score.types import FlowScore
from engine.greeks import delta as bs_delta
from engine.greeks import time_to_expiry_years
from engine.market_state.classify import MarketStateResult
from engine.profiles import UserStrategyProfile
from engine.regimes import Regime
from engine.strike_selector.types import LegSide, StrikeLeg
from engine.types import ChainSnapshot, OptionContract, OptionType

from .leg_factory import make_long_put, make_short_call
from .types import CollarIntent, CollarStructure

# Liquidity floors — V1 calibration. The M1.7 / M1.11 downgrade
# threshold sits at 0.50; our **filter** threshold is intentionally
# slightly lower (0.40) so the solver doesn't degenerate to empty on
# narrow-but-passable chains. M1.11's per-aggregate downgrade callback
# (M1.12 ladder) is the production safety net at 0.50 — we surface
# pairs above 0.40 here and let downgrades handle the marginal ones.
# Phase 4 / ME calibration may re-tighten this to 0.50.
MIN_LIQUIDITY_SCORE = 0.4
MIN_FILL_CONFIDENCE = 0.4

# Intent-specific short-call deltas. The profile doesn't currently
# expose `delta_target_band` (see dev spec §"Profile field mapping"),
# so we use intent-driven defaults: zero-cost = balanced, income =
# closer-to-ATM (more premium), defensive = further-OTM (let stock run).
INTENT_TARGET_CALL_DELTA: dict[CollarIntent, float] = {
    CollarIntent.ZERO_COST: 0.25,
    CollarIntent.INCOME: 0.35,
    CollarIntent.DEFENSIVE: 0.20,
}
# Band width widened from 0.10 → 0.15 in M1.11b to absorb realistic
# Black-Scholes-vs-proxy delta variance (typically 5–10% per strike).
# The dispatcher in `decision.produce()` now threads BS deltas via
# `engine.greeks.delta()` (M1.11b recommendation #1); a 0.10 band was
# too tight to admit pairs whose BS delta straddled the boundary.
DELTA_BAND_WIDTH = 0.15  # ±0.075 around the target

# Per-intent constraints (per plan §9.10).
ZERO_COST_TOLERANCE = 0.10
INCOME_MIN_CAPPED_UPSIDE_PCT = 0.04
DEFENSIVE_MAX_DEBIT_PCT = 0.005


def _estimate_delta(
    contract: OptionContract,
    spot: float,
    as_of: date,
    risk_free_rate: float = 0.05,
    dividend_yield: float = 0.0,
) -> float:
    """Estimate the signed delta for a chain contract.

    M1.11b recommendation #1: when the contract carries an `iv` and the
    chain's `as_of` is sane, compute the Black-Scholes delta via
    `engine.greeks.delta()`. Fall back to a moneyness-monotone proxy
    when IV is absent (e.g. chain feeds that publish only quotes).

    The proxy is intentionally crude (off by 5–15% vs BS for typical
    MSFT IV) but preserves ordering — so band membership is still
    monotone in strike. The proxy + the widened DELTA_BAND_WIDTH (M1.11b)
    keep V1 fixture tests stable even when iv is omitted.
    """
    if contract.iv is not None and contract.iv > 0:
        tau = time_to_expiry_years(as_of=as_of, expiry=contract.expiry)
        return bs_delta(
            spot=spot,
            strike=contract.strike,
            tau=tau,
            iv=contract.iv,
            r=risk_free_rate,
            q=dividend_yield,
            option_type=contract.option_type,
        )
    # Fallback proxy — used when iv is absent. Calls in (0.01, 0.99);
    # puts in (-0.99, -0.01).
    if contract.option_type is OptionType.CALL:
        moneyness = (spot - contract.strike) / spot
        return max(0.01, min(0.99, 0.5 + 4.0 * moneyness))
    moneyness = (contract.strike - spot) / spot
    return -max(0.01, min(0.99, 0.5 + 4.0 * moneyness))


# M1.11a-era alias preserved for backward compatibility of any caller
# that imported the V1 proxy directly. New code should call
# `_estimate_delta()` so the BS path is used when IV is available.
def _approx_delta(contract: OptionContract, spot: float) -> float:
    """Backward-compat shim — pre-M1.11b proxy. New code should call
    `_estimate_delta()` so Black-Scholes is used when IV is present."""
    if contract.option_type is OptionType.CALL:
        moneyness = (spot - contract.strike) / spot
        return max(0.01, min(0.99, 0.5 + 4.0 * moneyness))
    moneyness = (contract.strike - spot) / spot
    return -max(0.01, min(0.99, 0.5 + 4.0 * moneyness))


def _mid_of(contract: OptionContract) -> float:
    """Bid-ask midpoint, fallback to `mid`, fallback to 0.0."""
    if contract.bid is not None and contract.ask is not None:
        return (contract.bid + contract.ask) / 2.0
    if contract.mid is not None:
        return contract.mid
    return 0.0


def _candidate_expirations(chain: ChainSnapshot, horizon_days: int) -> list[date]:
    """Distinct chain expirations within `(0, horizon_days]` days of
    `chain.as_of`, sorted nearest-first."""
    raw = {c.expiry for c in chain.contracts}
    filtered = []
    for exp in raw:
        dte = (exp - chain.as_of).days
        if 0 < dte <= horizon_days:
            filtered.append(exp)
    return sorted(filtered)


def _filter_calls_for_intent(
    chain: ChainSnapshot,
    expiry: date,
    spot: float,
    intent: CollarIntent,
    *,
    risk_free_rate: float = 0.05,
    dividend_yield: float = 0.0,
) -> list[tuple[OptionContract, float]]:
    """Return `(contract, signed_delta)` for OTM calls whose delta
    falls within the intent's target band. Uses Black-Scholes deltas
    via `_estimate_delta()` when the chain publishes IV (M1.11b);
    falls back to the moneyness proxy otherwise."""
    target = INTENT_TARGET_CALL_DELTA[intent]
    lower = target - DELTA_BAND_WIDTH / 2.0
    upper = target + DELTA_BAND_WIDTH / 2.0
    out: list[tuple[OptionContract, float]] = []
    for c in chain.contracts:
        if c.option_type is not OptionType.CALL or c.expiry != expiry:
            continue
        if c.strike <= spot:
            continue
        d = _estimate_delta(c, spot, chain.as_of, risk_free_rate, dividend_yield)
        if lower <= d <= upper:
            out.append((c, d))
    return out


def _filter_puts_for_intent(
    chain: ChainSnapshot,
    expiry: date,
    spot: float,
    intent: CollarIntent,
    profile: UserStrategyProfile,
    *,
    risk_free_rate: float = 0.05,
    dividend_yield: float = 0.0,
) -> list[tuple[OptionContract, float]]:
    """Return `(contract, signed_delta)` for OTM puts that meet the
    intent's minimum downside protection. Uses Black-Scholes deltas
    via `_estimate_delta()` when IV is published (M1.11b)."""
    if intent is CollarIntent.INCOME:
        min_protection = profile.drawdown_tolerance / 2.0
    else:
        min_protection = profile.drawdown_tolerance
    out: list[tuple[OptionContract, float]] = []
    for c in chain.contracts:
        if c.option_type is not OptionType.PUT or c.expiry != expiry:
            continue
        if c.strike >= spot:
            continue
        protected_pct = (spot - c.strike) / spot
        if protected_pct < min_protection:
            continue
        d = _estimate_delta(c, spot, chain.as_of, risk_free_rate, dividend_yield)
        out.append((c, d))
    return out


def _confidence_inputs(
    market_state: MarketStateResult,
    flow_score: FlowScore,
    execution: Execution,
    intent: CollarIntent,
) -> ConfidenceInputs:
    """Project upstream signals into `ConfidenceInputs` shaped for
    the M1.10 Confidence Composer.

    V1 heuristics (not yet calibrated; superseded when ME1.x ships):

      flow_alignment:   collars protect downside → high when bias is
                        BEARISH or PIN_RISK.
      structure_alignment:
                        higher when spot is close to max_pain.
      regime_match:     high in HIGH_IV_EVENT / POST_EVENT_REPRICE
                        per plan §9.10 Integration.
      signal_alignment: scales with iv_rank — elevated IV makes the
                        zero-cost economics favorable.
      event_risk_penalty:
                        low for defensive intent in pre-event regimes
                        (a collar absorbs event risk).
      illiquidity_penalty:
                        derived from Execution.aggregate_fill_confidence.
    """
    # Flow alignment.
    if flow_score.bias.value in ("BEARISH", "PIN_RISK"):
        flow_alignment = 0.8
    elif flow_score.bias.value == "NEUTRAL":
        flow_alignment = 0.5
    else:
        flow_alignment = 0.3

    # Structure: closer-to-pin is better.
    structure_alignment = max(0.0, 1.0 - abs(market_state.max_pain_delta_pct) * 5.0)

    # Regime match. The 6 canonical regimes per ADR-0002 / §9.1 are
    # HIGH_IV_EVENT, HIGH_IV_PIN, LOW_IV_TREND, LOW_IV_RANGE, BREAKOUT,
    # POST_EVENT_REPRICE. Collars fit best when there's downside risk
    # (events, pins) or active vol; least useful in clean directional
    # regimes (TREND, BREAKOUT) where uncapped upside matters more.
    if market_state.regime in (Regime.HIGH_IV_EVENT, Regime.POST_EVENT_REPRICE):
        regime_match = 0.9
    elif market_state.regime in (Regime.HIGH_IV_PIN, Regime.LOW_IV_RANGE):
        regime_match = 0.6
    else:
        regime_match = 0.4

    # Signal: IV rank in [0, 100] → [0, 1].
    signal_alignment = min(1.0, max(0.0, market_state.iv_rank / 100.0))

    # Event risk — defensive collars absorb it well, so penalty is low.
    days_to_event = market_state.days_to_next_event
    if days_to_event is None or days_to_event > 30:
        event_risk_penalty = 0.10
    elif intent is CollarIntent.DEFENSIVE:
        event_risk_penalty = 0.05
    else:
        event_risk_penalty = 0.20

    # Illiquidity from Execution.
    illiquidity_penalty = max(0.0, 1.0 - execution.aggregate_fill_confidence)

    return ConfidenceInputs(
        flow_alignment=flow_alignment,
        structure_alignment=structure_alignment,
        regime_match=regime_match,
        signal_alignment=signal_alignment,
        event_risk_penalty=event_risk_penalty,
        illiquidity_penalty=illiquidity_penalty,
    )


def _tie_break_score(
    market_state: MarketStateResult,
    execution: Execution,
) -> float:
    """Tie-break score per plan §9.10:
    `score = iv_score - event_score - illiquidity_penalty`.

    Range roughly [-1, 1]. Higher = better.
    """
    iv_component = market_state.iv_rank / 100.0
    dte = market_state.days_to_next_event
    if dte is None:
        event_component = 0.0
    elif dte <= 5:
        event_component = 0.5
    elif dte <= 14:
        event_component = 0.2
    else:
        event_component = 0.0
    illiquidity_component = max(0.0, 1.0 - execution.aggregate_fill_confidence)
    return iv_component - event_component - illiquidity_component


def _rationale_for_intent(
    intent: CollarIntent,
    *,
    put_strike: float,
    call_strike: float,
    net_debit_credit: float,
    protected_downside_pct: float,
    capped_upside_pct: float,
) -> tuple[str, ...]:
    common_protection = (
        f"Protects {protected_downside_pct:.1%} downside via long {put_strike:.2f} put."
    )
    common_cap = (
        f"Capped upside above {call_strike:.2f} ({capped_upside_pct:.1%} from spot)."
    )
    if intent is CollarIntent.ZERO_COST:
        return (
            common_protection,
            common_cap,
            f"Near-zero net premium ({net_debit_credit:+.2f}/share) — short call funds the put.",
        )
    if intent is CollarIntent.INCOME:
        return (
            common_protection,
            common_cap,
            f"Net credit of {-net_debit_credit:.2f}/share — collar pays you to hold protection.",
        )
    return (
        common_protection,
        common_cap,
        f"Deeper downside floor in exchange for {net_debit_credit:+.2f}/share net cost.",
    )


def _risks_for_intent(
    intent: CollarIntent,
    *,
    call_strike: float,
    capped_upside_pct: float,
) -> tuple[str, ...]:
    cap_risk = (
        f"Upside capped at {call_strike:.2f} — gives up rally above {capped_upside_pct:.1%}."
    )
    if intent is CollarIntent.INCOME:
        return (
            cap_risk,
            "Net credit reduces but does not eliminate downside loss above the put strike.",
            "Early assignment risk on the short call if it goes deep ITM.",
        )
    return (
        cap_risk,
        "Long put can lose value rapidly if IV drops post-event.",
        "Early assignment risk on the short call if it goes deep ITM.",
    )


_INVALIDATION: tuple[str, ...] = (
    "Spot moves below long put strike before expiry → re-evaluate roll.",
    "Implied vol collapses post-event → consider closing short call early.",
    "Position size changes (e.g., partial sale) → resize the collar.",
)


def _strike_leg(
    contract: OptionContract,
    side: LegSide,
    delta_signed: float,
    mid: float,
    dte_actual: int,
) -> StrikeLeg:
    return StrikeLeg(
        contract=contract,
        side=side,
        delta_target=delta_signed,
        delta_actual=delta_signed,
        delta_distance=0.0,
        dte_actual=dte_actual,
        mid_price=mid,
    )


def _passes_liquidity_floors(execution: Execution) -> bool:
    if execution.aggregate_liquidity_score < MIN_LIQUIDITY_SCORE:
        return False
    if execution.aggregate_fill_confidence < MIN_FILL_CONFIDENCE:
        return False
    return True


def _build_structure(
    *,
    spot: float,
    chain_as_of: date,
    put_contract: OptionContract,
    put_delta: float,
    call_contract: OptionContract,
    call_delta: float,
    contracts: int,
    intent: CollarIntent,
    profile: UserStrategyProfile,
    market_state: MarketStateResult,
    flow_score: FlowScore,
    weights: Weights,
) -> CollarStructure:
    """Assemble a complete `CollarStructure` from the chosen leg pair.

    Computes per-share P&L, breakevens, Execution Feasibility,
    Confidence composition, and tie-break score. The pair is assumed
    to share an expiration (caller's responsibility).
    """
    long_put = make_long_put(put_contract, contracts, delta=put_delta)
    short_call = make_short_call(call_contract, contracts, delta=call_delta)

    # Net premium per share: long-put is +mid, short-call is -mid.
    net_debit_credit = long_put.premium + short_call.premium

    # Per-share P&L at expiry. P&L includes the net premium paid/received.
    max_gain = (short_call.strike - spot) - net_debit_credit
    max_loss = (long_put.strike - spot) - net_debit_credit

    # Both breakevens are the same at entry (net premium shifts the
    # entire payoff curve).
    upside_breakeven = spot + net_debit_credit
    downside_breakeven = spot + net_debit_credit

    capped_upside_pct = (short_call.strike - spot) / spot
    protected_downside_pct = (spot - long_put.strike) / spot

    # M1.11 Execution Feasibility — combined legs.
    dte = (put_contract.expiry - chain_as_of).days
    put_leg = _strike_leg(put_contract, LegSide.LONG, put_delta, long_put.mid, dte)
    call_leg = _strike_leg(call_contract, LegSide.SHORT, call_delta, short_call.mid, dte)
    execution = assess(legs=[put_leg, call_leg], quantities=[contracts, contracts])

    # M1.10 Confidence Composer.
    conf_inputs = _confidence_inputs(market_state, flow_score, execution, intent)
    confidence, breakdown = compose(conf_inputs, weights)

    # Tie-break.
    score = _tie_break_score(market_state, execution)

    # Name: "Zero-cost 30d collar 405/430"
    pretty_intent = intent.value.replace("_", "-").capitalize()
    name = (
        f"{pretty_intent} {dte}d collar "
        f"{long_put.strike:.0f}/{short_call.strike:.0f}"
    )

    return CollarStructure(
        name=name,
        intent=intent,
        horizon_days=dte,
        long_put=long_put,
        short_call=short_call,
        net_debit_credit=net_debit_credit,
        max_gain=max_gain,
        max_loss=max_loss,
        upside_breakeven=upside_breakeven,
        downside_breakeven=downside_breakeven,
        capped_upside_pct=capped_upside_pct,
        protected_downside_pct=protected_downside_pct,
        confidence=confidence,
        confidence_breakdown=breakdown,
        rationale=_rationale_for_intent(
            intent,
            put_strike=long_put.strike,
            call_strike=short_call.strike,
            net_debit_credit=net_debit_credit,
            protected_downside_pct=protected_downside_pct,
            capped_upside_pct=capped_upside_pct,
        ),
        risks=_risks_for_intent(
            intent,
            call_strike=short_call.strike,
            capped_upside_pct=capped_upside_pct,
        ),
        invalidation=_INVALIDATION,
        execution=execution,
        score=score,
    )


def solve_zero_cost(
    *,
    spot: float,
    chain: ChainSnapshot,
    contracts: int,
    profile: UserStrategyProfile,
    market_state: MarketStateResult,
    flow_score: FlowScore,
    expirations: Iterable[date],
    weights: Weights,
    risk_free_rate: float = 0.05,
    dividend_yield: float = 0.0,
) -> CollarStructure | None:
    """Find the pair with `|net_debit_credit| ≤ ZERO_COST_TOLERANCE`.
    Tie-break by tie-break score."""
    best: CollarStructure | None = None
    best_residual = float("inf")
    for exp in expirations:
        calls = _filter_calls_for_intent(
            chain, exp, spot, CollarIntent.ZERO_COST,
            risk_free_rate=risk_free_rate, dividend_yield=dividend_yield,
        )
        puts = _filter_puts_for_intent(
            chain, exp, spot, CollarIntent.ZERO_COST, profile,
            risk_free_rate=risk_free_rate, dividend_yield=dividend_yield,
        )
        for call_contract, call_delta in calls:
            call_mid = _mid_of(call_contract)
            for put_contract, put_delta in puts:
                put_mid = _mid_of(put_contract)
                # Pre-screen: skip pairs that obviously can't satisfy
                # the ±tolerance even without execution costs.
                if abs(put_mid - call_mid) > ZERO_COST_TOLERANCE:
                    continue
                structure = _build_structure(
                    spot=spot,
                    chain_as_of=chain.as_of,
                    put_contract=put_contract,
                    put_delta=put_delta,
                    call_contract=call_contract,
                    call_delta=call_delta,
                    contracts=contracts,
                    intent=CollarIntent.ZERO_COST,
                    profile=profile,
                    market_state=market_state,
                    flow_score=flow_score,
                    weights=weights,
                )
                if not _passes_liquidity_floors(structure.execution):
                    continue
                residual = abs(structure.net_debit_credit)
                if residual < best_residual:
                    best = structure
                    best_residual = residual
                elif (
                    residual == best_residual
                    and best is not None
                    and structure.score > best.score
                ):
                    best = structure
    return best


def solve_income(
    *,
    spot: float,
    chain: ChainSnapshot,
    contracts: int,
    profile: UserStrategyProfile,
    market_state: MarketStateResult,
    flow_score: FlowScore,
    expirations: Iterable[date],
    weights: Weights,
    risk_free_rate: float = 0.05,
    dividend_yield: float = 0.0,
) -> CollarStructure | None:
    """Find the pair that maximizes net credit (most-negative
    `net_debit_credit`) subject to:
      - `capped_upside_pct ≥ INCOME_MIN_CAPPED_UPSIDE_PCT`
      - `protected_downside_pct ≥ profile.drawdown_tolerance / 2`
      - liquidity floors.
    """
    best: CollarStructure | None = None
    best_credit = 0.0
    for exp in expirations:
        calls = _filter_calls_for_intent(
            chain, exp, spot, CollarIntent.INCOME,
            risk_free_rate=risk_free_rate, dividend_yield=dividend_yield,
        )
        puts = _filter_puts_for_intent(
            chain, exp, spot, CollarIntent.INCOME, profile,
            risk_free_rate=risk_free_rate, dividend_yield=dividend_yield,
        )
        for call_contract, call_delta in calls:
            for put_contract, put_delta in puts:
                structure = _build_structure(
                    spot=spot,
                    chain_as_of=chain.as_of,
                    put_contract=put_contract,
                    put_delta=put_delta,
                    call_contract=call_contract,
                    call_delta=call_delta,
                    contracts=contracts,
                    intent=CollarIntent.INCOME,
                    profile=profile,
                    market_state=market_state,
                    flow_score=flow_score,
                    weights=weights,
                )
                if structure.capped_upside_pct < INCOME_MIN_CAPPED_UPSIDE_PCT:
                    continue
                if not _passes_liquidity_floors(structure.execution):
                    continue
                if structure.net_debit_credit < best_credit:
                    best = structure
                    best_credit = structure.net_debit_credit
                elif (
                    structure.net_debit_credit == best_credit
                    and best is not None
                    and structure.score > best.score
                ):
                    best = structure
    return best


def solve_defensive(
    *,
    spot: float,
    chain: ChainSnapshot,
    contracts: int,
    profile: UserStrategyProfile,
    market_state: MarketStateResult,
    flow_score: FlowScore,
    expirations: Iterable[date],
    weights: Weights,
    position_notional: float | None = None,
    risk_free_rate: float = 0.05,
    dividend_yield: float = 0.0,
) -> CollarStructure | None:
    """Find the pair that maximizes `protected_downside_pct` subject
    to `net_debit ≤ DEFENSIVE_MAX_DEBIT_PCT * position_notional`
    (per share, scaled to position) + liquidity floors."""
    if position_notional is None:
        position_notional = spot * contracts * 100.0
    max_debit_per_share = (DEFENSIVE_MAX_DEBIT_PCT * position_notional) / (
        contracts * 100.0
    )

    best: CollarStructure | None = None
    best_protection = 0.0
    for exp in expirations:
        calls = _filter_calls_for_intent(
            chain, exp, spot, CollarIntent.DEFENSIVE,
            risk_free_rate=risk_free_rate, dividend_yield=dividend_yield,
        )
        puts = _filter_puts_for_intent(
            chain, exp, spot, CollarIntent.DEFENSIVE, profile,
            risk_free_rate=risk_free_rate, dividend_yield=dividend_yield,
        )
        for call_contract, call_delta in calls:
            for put_contract, put_delta in puts:
                structure = _build_structure(
                    spot=spot,
                    chain_as_of=chain.as_of,
                    put_contract=put_contract,
                    put_delta=put_delta,
                    call_contract=call_contract,
                    call_delta=call_delta,
                    contracts=contracts,
                    intent=CollarIntent.DEFENSIVE,
                    profile=profile,
                    market_state=market_state,
                    flow_score=flow_score,
                    weights=weights,
                )
                if structure.net_debit_credit > max_debit_per_share:
                    continue
                if not _passes_liquidity_floors(structure.execution):
                    continue
                if structure.protected_downside_pct > best_protection:
                    best = structure
                    best_protection = structure.protected_downside_pct
                elif (
                    structure.protected_downside_pct == best_protection
                    and best is not None
                    and structure.score > best.score
                ):
                    best = structure
    return best
