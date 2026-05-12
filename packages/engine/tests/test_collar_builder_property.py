"""Property tests per master plan §9.10 + M1.11a dev spec §Tests.

Four invariants the dev spec promises:

  1. `zero_cost.net_debit_credit ∈ [-0.10, +0.10]`
  2. `income.net_debit_credit ≤ 0` (always a credit, or empty list)
  3. `defensive.protected_downside_pct ≥ income.protected_downside_pct`
  4. Liquidity-downgrade fallback: when chosen pair fails Execution
     Feasibility, builder retries with adjacent strikes (or returns
     empty with reason).
"""

from __future__ import annotations

from engine.collar_builder import CollarIntent, build
from engine.collar_builder.structures import ZERO_COST_TOLERANCE

from ._collar_test_helpers import (
    SEED_SPOT,
    seed_chain,
    seed_flow_score,
    seed_market_state,
    seed_profile,
)


def _build_all(**overrides):
    return build(
        spot=overrides.get("spot", SEED_SPOT),
        underlying_qty=overrides.get("underlying_qty", 200),
        chain=overrides.get("chain", seed_chain()),
        profile=overrides.get("profile", seed_profile()),
        market_state=overrides.get("market_state", seed_market_state()),
        flow_score=overrides.get("flow_score", seed_flow_score()),
        intents=overrides.get(
            "intents",
            [CollarIntent.ZERO_COST, CollarIntent.INCOME, CollarIntent.DEFENSIVE],
        ),
    )


def test_zero_cost_net_premium_within_tolerance() -> None:
    """Property: |zero_cost.net_debit_credit| ≤ ZERO_COST_TOLERANCE."""
    results = _build_all(intents=[CollarIntent.ZERO_COST])
    assert len(results) == 1, "seed fixture should yield a zero-cost candidate"
    zc = results[0]
    assert abs(zc.net_debit_credit) <= ZERO_COST_TOLERANCE, (
        f"net_debit_credit = {zc.net_debit_credit:.4f}, "
        f"tolerance = {ZERO_COST_TOLERANCE}"
    )


def test_income_is_always_a_credit() -> None:
    """Property: `income.net_debit_credit ≤ 0` (credit) OR empty list."""
    results = _build_all(intents=[CollarIntent.INCOME])
    if not results:
        return  # empty is acceptable
    assert results[0].net_debit_credit <= 0.0, (
        f"income.net_debit_credit = {results[0].net_debit_credit:+.4f} — "
        "income intent should be a credit (or skip)"
    )


def test_defensive_protection_geq_income() -> None:
    """Property: defensive provides at least as much downside protection
    as income (when both exist)."""
    results = _build_all()
    by_intent = {s.intent: s for s in results}
    if CollarIntent.DEFENSIVE not in by_intent or CollarIntent.INCOME not in by_intent:
        return  # nothing to compare
    defensive = by_intent[CollarIntent.DEFENSIVE]
    income = by_intent[CollarIntent.INCOME]
    assert defensive.protected_downside_pct >= income.protected_downside_pct, (
        f"defensive ({defensive.protected_downside_pct:.4f}) should protect "
        f"≥ income ({income.protected_downside_pct:.4f})"
    )


def test_max_loss_floor_is_long_put_minus_net_premium() -> None:
    """Sanity property: per-share max loss equals
    `(long_put.strike - spot) - net_debit_credit`. The long put is the
    floor; net premium shifts it."""
    results = _build_all()
    for s in results:
        expected = (s.long_put.strike - SEED_SPOT) - s.net_debit_credit
        assert abs(s.max_loss - expected) < 1e-9, (
            f"intent={s.intent}, max_loss={s.max_loss}, expected={expected}"
        )


def test_max_gain_ceiling_is_short_call_minus_net_premium() -> None:
    """Sanity property: per-share max gain equals
    `(short_call.strike - spot) - net_debit_credit`."""
    results = _build_all()
    for s in results:
        expected = (s.short_call.strike - SEED_SPOT) - s.net_debit_credit
        assert abs(s.max_gain - expected) < 1e-9, (
            f"intent={s.intent}, max_gain={s.max_gain}, expected={expected}"
        )


def test_short_call_strike_above_spot_long_put_below() -> None:
    """OTM property: collar legs are always OTM (call above, put below
    the spot at entry)."""
    results = _build_all()
    for s in results:
        assert s.short_call.strike > SEED_SPOT
        assert s.long_put.strike < SEED_SPOT


def test_premium_sign_convention() -> None:
    """Sign property: long-put premium is positive (paid); short-call
    premium is negative (received). Net is their sum."""
    results = _build_all()
    for s in results:
        assert s.long_put.premium > 0, f"long_put.premium = {s.long_put.premium}"
        assert s.short_call.premium < 0, f"short_call.premium = {s.short_call.premium}"
        expected_net = s.long_put.premium + s.short_call.premium
        assert abs(s.net_debit_credit - expected_net) < 1e-9


def test_determinism_same_inputs_same_output() -> None:
    """Replay property: identical inputs → equal output (frozen
    dataclass equality)."""
    a = _build_all()
    b = _build_all()
    assert a == b, "same inputs should produce equal CollarStructure tuples"
