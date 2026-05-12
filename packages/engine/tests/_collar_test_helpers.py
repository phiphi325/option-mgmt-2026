"""Shared test helpers for the collar_builder test suite.

Underscore prefix → pytest does not collect this as a test module.

Provides:
  - `seed_chain()`       a realistic 30-day MSFT chain with engineered
                         premiums that exercise all three solvers.
  - `seed_profile()`     a `UserStrategyProfile` with low
                         `drawdown_tolerance` so the seed chain's
                         puts qualify as protective.
  - `seed_market_state()` and `seed_flow_score()` — minimal upstream
                         inputs.
"""

from __future__ import annotations

from datetime import date

from engine.flow_score.types import Bias, FlowScore, RecommendedAction
from engine.market_state.classify import MarketStateResult
from engine.profiles import (
    IncomeNeed,
    ProfileStyle,
    RiskTolerance,
    UserStrategyProfile,
)
from engine.regimes import Regime
from engine.types import ChainSnapshot, OptionContract, OptionType

# Spot, as-of date, and expiry are fixed across all helpers.
SEED_SPOT: float = 400.0
SEED_AS_OF: date = date(2026, 5, 20)
SEED_EXPIRY: date = date(2026, 6, 19)  # 30 days out


def _put(strike: float, bid: float, ask: float, oi: int = 5000, vol: int = 1000) -> OptionContract:
    """Build a PUT contract for the seed chain.

    Defaults (OI=5000, vol=1000) are generously liquid so M1.11
    Execution Feasibility passes the 0.5 floors comfortably.
    """
    return OptionContract(
        underlying="MSFT",
        expiry=SEED_EXPIRY,
        strike=strike,
        option_type=OptionType.PUT,
        bid=bid,
        ask=ask,
        iv=0.30,
        open_interest=oi,
        volume=vol,
    )


def _call(strike: float, bid: float, ask: float, oi: int = 5000, vol: int = 1000) -> OptionContract:
    return OptionContract(
        underlying="MSFT",
        expiry=SEED_EXPIRY,
        strike=strike,
        option_type=OptionType.CALL,
        bid=bid,
        ask=ask,
        iv=0.30,
        open_interest=oi,
        volume=vol,
    )


def seed_chain() -> ChainSnapshot:
    """Engineered 30-day chain.

    Strikes 360..440 spaced 5-10 apart around spot 400. Premiums set
    so each solver has a clean winning pair:

      ZERO_COST:  380P @ 1.00  +  420C @ 1.00  →  net 0.00
      INCOME:     380P @ 1.00  +  410C @ 3.00  →  net -2.00 (credit)
      DEFENSIVE:  360P @ 0.50  +  430C @ 0.40  →  net +0.10 (debit, deep protection)

    Approx-delta proxy for short-call delta bands (per
    `_approx_delta` in structures.py):
      410C → 0.40, 420C → 0.30, 430C → 0.20.
    ZERO_COST band [0.20, 0.30]: 420 + 430 in band.
    INCOME band   [0.30, 0.40]: 410 + 420 in band.
    DEFENSIVE band [0.15, 0.25]: 430 in band.
    """
    # 1-cent spreads (0.005 each side) on every leg so spread_bps stays
    # below the M1.11 §9.8 cap of 300 even on the cheaper OTM options.
    # The mid-prices are set so the three solvers each find a clean
    # winning pair (see helpers docstring).
    contracts: tuple[OptionContract, ...] = (
        # PUTs — protective floors; lower strikes = deeper protection.
        _put(strike=360.0, bid=0.495, ask=0.505),  # mid 0.50; 10% protection
        _put(strike=370.0, bid=0.795, ask=0.805),  # mid 0.80;  7.5% protection
        _put(strike=380.0, bid=0.995, ask=1.005),  # mid 1.00;  5% protection
        _put(strike=390.0, bid=1.495, ask=1.505),  # mid 1.50;  2.5% protection
        _put(strike=395.0, bid=1.995, ask=2.005),  # mid 2.00;  1.25% protection
        # CALLs — upside caps; higher strikes = more room.
        _call(strike=405.0, bid=3.995, ask=4.005),  # mid 4.00
        _call(strike=410.0, bid=2.995, ask=3.005),  # mid 3.00
        _call(strike=420.0, bid=0.995, ask=1.005),  # mid 1.00
        _call(strike=430.0, bid=0.395, ask=0.405),  # mid 0.40
        _call(strike=440.0, bid=0.145, ask=0.155),  # mid 0.15
    )
    return ChainSnapshot(
        underlying="MSFT",
        spot=SEED_SPOT,
        as_of=SEED_AS_OF,
        contracts=contracts,
    )


def seed_profile(
    *,
    drawdown_tolerance: float = 0.05,
    max_coverage_pct: float = 1.0,
) -> UserStrategyProfile:
    """Profile with low drawdown tolerance so 5%+ OTM puts qualify."""
    return UserStrategyProfile(
        risk_tolerance=RiskTolerance.MODERATE,
        income_need=IncomeNeed.MEDIUM,
        max_position_pct=1.0,
        max_coverage_pct=max_coverage_pct,
        min_iv_rank_for_short_premium=30,
        prefer_collars_over_covered_calls=True,
        drawdown_tolerance=drawdown_tolerance,
        style=ProfileStyle.BALANCED,
    )


def seed_market_state(
    *,
    regime: Regime = Regime.HIGH_IV_EVENT,
    iv_rank: float = 70.0,
    days_to_event: int | None = 7,
) -> MarketStateResult:
    """Minimal upstream market state for collar tests."""
    return MarketStateResult(
        regime=regime,
        regime_score=0.82,
        all_scores={r: 0.0 for r in Regime},
        tags=("collar_test_fixture",),
        spot=SEED_SPOT,
        iv_rank=iv_rank,
        iv_percentile=iv_rank,
        hv_30=0.25,
        expected_move_pct=0.045,
        max_pain=400.0,
        max_pain_delta_pct=0.0,
        pcr_volume=1.1,
        pcr_oi=1.0,
        trend_strength=0.0,
        realized_vs_implied=0.95,
        breakout_signal=0.0,
        oi_concentration_at_max_pain=0.3,
        days_to_next_event=days_to_event,
        next_event_kind="earnings" if days_to_event is not None else None,
        days_since_event=None,
        days_to_nearest_opex=14,
        iv_rank_change_1d=2.0,
        gap_pct=0.0,
    )


def seed_flow_score(*, bias: Bias = Bias.BEARISH) -> FlowScore:
    """Minimal flow score — BEARISH aligns with collar protection thesis."""
    return FlowScore(
        score=0.55,
        bullish_score=0.30,
        bearish_score=0.75,
        bias=bias,
        recommended_action=RecommendedAction.BUY_PROTECTION,
        pin_probability=0.20,
        gamma_risk=0.30,
        gamma_sign=-1,
        confidence=0.60,
        explanation="collar test fixture",
        breakdown={"iv": 0.5, "structure": 0.4, "gamma": 0.3, "event": 0.2},
    )
