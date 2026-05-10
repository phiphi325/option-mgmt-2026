"""Flow Score Engine — V1 LOCKED `compute()` orchestrator.

Per plan v1.2 §9.3a (V1 LOCKED contract), §17 M1.5b (size M), and §17 M1.6.

`compute()` wires the M1.5 primitives + M1.4a/M1.5a scoring primitives
into a single `FlowScore` result. Internal flow:

  1. Compute OI walls (M1.5 `compute_oi_walls`).
  2. Compute max-pain from the chain (M1.2 `compute_max_pain`).
  3. Compute PCR (M1.2 `pcr_volume`, `pcr_oi`).
  4. Compute 25-Δ skew (M1.6 `skew_25d`) + futures-basis stub.
  5. Compute dealer-gamma proxy (M1.5 `compute_dealer_gamma_proxy`).
  6. Compute `gamma_score` (M1.5a) on that proxy.
  7. Score the 5-component bullish + bearish formulas (§9.3a weights).
  8. Pin probability from `sigmoid_pin`.
  9. Bias bucketing from signed `score` + pin probability.
  10. Decision tree → `recommended_action`.
  11. Confidence from total OI in focus.
  12. Render explanation.

Output: `FlowScore` (frozen dataclass, see `types.py`).

## Calibration notes

The §9.3a 5-component weights for each side:

    bullish weights: 0.30 + 0.25 + 0.20 + 0.15 + 0.10 = 1.0  →  bullish ∈ [0, 100]
    bearish weights:                  (symmetric)            →  bearish ∈ [0, 100]

As of M1.6, `skew_25d` (the 0.20 component) is **active** — it computes
real 25-delta IV skew using the new `engine.greeks` module. The
`futures_basis` (the 0.15 component) remains a V1 stub returning 0
until Phase 2 wires up the futures service. With four of five
components active, max bullish/bearish each cap at
`(0.30 + 0.25 + 0.20 + 0.10) * 100 = 85`. The math is
forward-compatible: when the Phase 2 futures service lands, the full
5-component math activates without recalibration.

## Bias thresholds

    BULLISH:   score >= +20  AND pin_probability  < 0.6
    BEARISH:   score <= -20  AND pin_probability  < 0.6
    PIN_RISK:                     pin_probability >= 0.6
    NEUTRAL:   everything else

These threshold values are V1 priors; the Phase 4 ML upgrade (per
ADR-0008) trains them or replaces with a learned classifier.

## Decision tree

Matches §9.3a verbatim — first match wins:

    score >= +40 AND gamma_risk <= 0.5  → SELL_CALL_AGGRESSIVE
    score >= +10                        → SELL_CALL_PARTIAL
    score in (-10, +10) AND pin >= 0.6  → WAIT
    score <= -20 AND gamma_risk >= 0.6  → BUY_PROTECTION
    score <= -10                        → REDUCE_COVERAGE
    otherwise                           → MONITOR

Pure function (per ADR-0005). No I/O.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from engine._utils import clip01
from engine.flow_score.dealer_gamma import compute_dealer_gamma_proxy
from engine.flow_score.explanation import render_explanation
from engine.flow_score.futures_basis import futures_basis
from engine.flow_score.oi_walls import compute_oi_walls
from engine.flow_score.pin_probability import sigmoid_pin
from engine.flow_score.skew import skew_25d
from engine.flow_score.types import Bias, FlowScore, RecommendedAction
from engine.market_state.max_pain import compute_max_pain
from engine.market_state.pcr import pcr_oi, pcr_volume
from engine.scoring.gamma import gamma_score
from engine.types import ChainSnapshot, OptionContract, OptionType

# Bullish / bearish weights (sum to 1.0 per §9.3a). See module docstring.
_W_DIST = 0.30
_W_VOL = 0.25
_W_SKEW = 0.20
_W_BASIS = 0.15
_W_PCR = 0.10

# Wall-distance normalization. dist_pct >= _WALL_FAR_PCT → 1.0 (lots of
# room); dist_pct == 0 (spot on wall) → 0.0; linear between.
_WALL_FAR_PCT = 0.05

# One-sided-wall fallback. When the wall on the relevant side is None,
# the wall-distance contribution is the "no information" prior (0.5)
# rather than 0 or 1.
_WALL_MISSING_PRIOR = 0.5

# Confidence normalization. Total OI in focus divided by this scale,
# clipped to [0, 1]. 100,000 OI → 1.0 confidence; smaller chains scale
# linearly. Phase 4 ML may replace this with a logistic.
_CONFIDENCE_OI_SCALE = 100_000

# Bias thresholds (V1 priors; see module docstring).
_BIAS_BULLISH_THRESHOLD = 20.0
_BIAS_BEARISH_THRESHOLD = -20.0
_BIAS_PIN_THRESHOLD = 0.6

# Decision-tree thresholds (per §9.3a).
_ACTION_AGGRESSIVE_SCORE = 40.0
_ACTION_AGGRESSIVE_GAMMA = 0.5
_ACTION_PARTIAL_SCORE = 10.0
_ACTION_WAIT_SCORE_BAND = 10.0  # |score| < this → WAIT (when pin high)
_ACTION_WAIT_PIN = 0.6
_ACTION_PROTECTION_SCORE = -20.0
_ACTION_PROTECTION_GAMMA = 0.6
_ACTION_REDUCE_SCORE = -10.0


# ----------------------------------------------------------------------
# Helper computations (small, individually testable)
# ----------------------------------------------------------------------


def _volume_shares(
    *,
    contracts: Sequence[OptionContract],
    expiry_focus: set[date],
) -> tuple[float, float]:
    """Return (call_share, put_share) of total volume in focus expiries.

    Each value is in [0, 1]; they sum to 1.0 when total volume > 0.
    When total volume is 0, both return 0.5 (neutral prior).
    """
    call_vol = 0
    put_vol = 0
    for c in contracts:
        if c.expiry not in expiry_focus:
            continue
        if c.option_type is OptionType.CALL:
            call_vol += c.volume
        else:
            put_vol += c.volume
    total = call_vol + put_vol
    if total == 0:
        return 0.5, 0.5
    return call_vol / total, put_vol / total


def _dist_to_wall_norm(*, spot: float, wall: float | None) -> float:
    """Normalized distance from spot to a wall.

    Returns 0 when spot is ON the wall, 1 when ≥ 5% away, linear
    in between. When the wall is `None`, returns the 0.5 neutral prior.
    """
    if wall is None:
        return _WALL_MISSING_PRIOR
    dist_pct = abs(wall - spot) / spot
    return clip01(dist_pct / _WALL_FAR_PCT)


def _oi_concentration_at_max_pain(
    *,
    contracts: Sequence[OptionContract],
    max_pain: float,
    expiry_focus: set[date],
) -> float:
    """Fraction of OI in focus expiries that sits at the max-pain strike.

    Returns 0 when total OI is 0.
    """
    at_pain_oi = 0
    total_oi = 0
    for c in contracts:
        if c.expiry not in expiry_focus:
            continue
        total_oi += c.open_interest
        if c.strike == max_pain:
            at_pain_oi += c.open_interest
    if total_oi == 0:
        return 0.0
    return at_pain_oi / total_oi


def _confidence_from_oi_total(
    *,
    contracts: Sequence[OptionContract],
    expiry_focus: set[date],
) -> float:
    """Confidence proxy: linear in total OI, clipped at 1.0."""
    total_oi = sum(c.open_interest for c in contracts if c.expiry in expiry_focus)
    return clip01(total_oi / _CONFIDENCE_OI_SCALE)


def _decide_bias(*, score: float, pin_probability: float) -> Bias:
    """Bucket the signed score + pin probability into a Bias enum."""
    if pin_probability >= _BIAS_PIN_THRESHOLD:
        return Bias.PIN_RISK
    if score >= _BIAS_BULLISH_THRESHOLD:
        return Bias.BULLISH
    if score <= _BIAS_BEARISH_THRESHOLD:
        return Bias.BEARISH
    return Bias.NEUTRAL


def _decide_action(
    *,
    score: float,
    gamma_risk: float,
    pin_probability: float,
) -> RecommendedAction:
    """Per §9.3a decision tree — first match wins."""
    if score >= _ACTION_AGGRESSIVE_SCORE and gamma_risk <= _ACTION_AGGRESSIVE_GAMMA:
        return RecommendedAction.SELL_CALL_AGGRESSIVE
    if score >= _ACTION_PARTIAL_SCORE:
        return RecommendedAction.SELL_CALL_PARTIAL
    if (
        abs(score) < _ACTION_WAIT_SCORE_BAND
        and pin_probability >= _ACTION_WAIT_PIN
    ):
        return RecommendedAction.WAIT
    if score <= _ACTION_PROTECTION_SCORE and gamma_risk >= _ACTION_PROTECTION_GAMMA:
        return RecommendedAction.BUY_PROTECTION
    if score <= _ACTION_REDUCE_SCORE:
        return RecommendedAction.REDUCE_COVERAGE
    return RecommendedAction.MONITOR


# ----------------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------------


def compute(
    *,
    chain_snapshot: ChainSnapshot,
    spot: float,
    expiry_focus: Sequence[date],
    dte_to_nearest_opex: int | None = None,
    risk_free_rate: float = 0.05,
    dividend_yield: float = 0.0,
) -> FlowScore:
    """V1 Flow Score Engine `compute()` per plan §9.3a.

    Args:
        chain_snapshot: Frozen option-chain projection. The engine never
                        touches the wire — the data layer hydrates this.
        spot: Current underlying spot. Must be > 0.
        expiry_focus: Iterable of expiries to scope the flow analysis to.
                      Must be non-empty.
        dte_to_nearest_opex: Trading days to the nearest monthly opex.
                             Passed through to `sigmoid_pin` to weigh
                             pin probability. `None` (default) when no
                             opex sits in the relevant horizon.
        risk_free_rate: Continuous-compounding risk-free rate. Default
                        `0.05` (V1 prior matching the early-2026 SOFR
                        baseline). Threaded through to `skew_25d` for
                        BS delta computation.
        dividend_yield: Continuous-compounding dividend yield. Default
                        `0.0` (sensible for MSFT-class names). Threaded
                        through to `skew_25d` for BS delta computation.

    Returns:
        `FlowScore` (frozen dataclass) with the full V1 LOCKED contract.

    Raises:
        ValueError: `spot` <= 0, `expiry_focus` empty, or no contracts
                    at any focus expiry (propagated from primitives).
    """
    if spot <= 0.0:
        raise ValueError(f"compute: spot must be > 0; got {spot}")
    focus = set(expiry_focus)
    if not focus:
        raise ValueError("compute: expiry_focus must contain at least one expiry")

    contracts = chain_snapshot.contracts

    # 1. OI walls.
    walls = compute_oi_walls(
        contracts=contracts,
        spot=spot,
        expiry_focus=expiry_focus,
    )

    # 2. Max pain. Use the first focus expiry; production deployments
    #    pass the relevant expiry. compute_max_pain raises if no
    #    contracts exist at that expiry — propagate the error rather
    #    than hide it.
    focus_list = sorted(focus)
    max_pain = compute_max_pain(contracts=contracts, expiry=focus_list[0])

    # 3. PCR.
    focus_contracts = [c for c in contracts if c.expiry in focus]
    pcrv = pcr_volume(contracts=focus_contracts)
    pcroi = pcr_oi(contracts=focus_contracts)

    # 4. 25-Δ skew (M1.6 real impl) + futures-basis stub.
    skew = skew_25d(
        contracts=contracts,
        expiry_focus=expiry_focus,
        spot=spot,
        as_of=chain_snapshot.as_of,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
    )
    basis = futures_basis(spot=spot)

    # 5. Dealer-gamma proxy.
    gamma_proxy = compute_dealer_gamma_proxy(
        contracts=contracts,
        spot=spot,
        expiry_focus=expiry_focus,
    )

    # 6. Gamma score (signed magnitude).
    gamma = gamma_score(
        dealer_gamma_proxy=gamma_proxy,
        spot=spot,
        gamma_walls=[],  # M1.5b consumes the V1 proxy only
    )

    # 7. 5-component bullish + bearish scores per §9.3a.
    call_share, put_share = _volume_shares(
        contracts=contracts, expiry_focus=focus
    )
    bullish_dist = _dist_to_wall_norm(spot=spot, wall=walls.resistance)
    bearish_dist = _dist_to_wall_norm(spot=spot, wall=walls.support)
    bullish_skew = max(0.0, -skew)
    bearish_skew = max(0.0, skew)
    bullish_basis = max(0.0, basis)
    bearish_basis = max(0.0, -basis)
    bullish_pcrv = max(0.0, 1.0 - pcrv) if pcrv <= 1.0 else 0.0
    bearish_pcrv = pcrv if pcrv <= 1.0 else 1.0

    bullish_raw = (
        _W_DIST * bullish_dist
        + _W_VOL * call_share
        + _W_SKEW * bullish_skew
        + _W_BASIS * bullish_basis
        + _W_PCR * bullish_pcrv
    )
    bearish_raw = (
        _W_DIST * bearish_dist
        + _W_VOL * put_share
        + _W_SKEW * bearish_skew
        + _W_BASIS * bearish_basis
        + _W_PCR * bearish_pcrv
    )
    bullish_score = clip01(bullish_raw) * 100.0
    bearish_score = clip01(bearish_raw) * 100.0
    score = bullish_score - bearish_score

    # 8. Pin probability.
    oi_conc = _oi_concentration_at_max_pain(
        contracts=contracts, max_pain=max_pain, expiry_focus=focus
    )
    pin_probability = sigmoid_pin(
        spot=spot,
        max_pain=max_pain,
        dte_to_nearest_opex=dte_to_nearest_opex,
        oi_concentration_at_max_pain=oi_conc,
    )

    # 9. Bias bucketing.
    bias = _decide_bias(score=score, pin_probability=pin_probability)

    # 10. Decision tree.
    gamma_risk = gamma.score
    recommended_action = _decide_action(
        score=score,
        gamma_risk=gamma_risk,
        pin_probability=pin_probability,
    )

    # 11. Confidence.
    confidence = _confidence_from_oi_total(
        contracts=contracts, expiry_focus=focus
    )

    # 12. Explanation.
    explanation = render_explanation(
        walls=walls,
        score=score,
        gamma=gamma,
        pin_probability=pin_probability,
    )

    breakdown = {
        "bullish_dist": bullish_dist,
        "bullish_call_vol": call_share,
        "bullish_skew": bullish_skew,
        "bullish_basis": bullish_basis,
        "bullish_pcrv": bullish_pcrv,
        "bearish_dist": bearish_dist,
        "bearish_put_vol": put_share,
        "bearish_skew": bearish_skew,
        "bearish_basis": bearish_basis,
        "bearish_pcrv": bearish_pcrv,
        "pcr_oi": pcroi,
        "oi_concentration_at_max_pain": oi_conc,
        "max_pain": max_pain,
    }

    return FlowScore(
        score=score,
        bullish_score=bullish_score,
        bearish_score=bearish_score,
        bias=bias,
        recommended_action=recommended_action,
        pin_probability=pin_probability,
        gamma_risk=gamma_risk,
        gamma_sign=gamma.sign,
        confidence=confidence,
        explanation=explanation,
        breakdown=breakdown,
    )
