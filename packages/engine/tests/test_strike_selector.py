"""Strike Selector tests (M1.7 / M1.9 — Action-based contract).

Per plan v1.2 §17 M1.7 acceptance and §9.4.

M1.9 refactored `select_strikes` to take an `Action` (from
`engine.recommendation`) instead of the prior `Recommendation` shape.
The leg-structure dispatch is keyed by `EmittedAction` codes. These
tests cover the M1.9 contract.

Test discipline (mirrors M1.4 / M1.5b / M1.6 / M1.7 patterns):
- Per-emit leg-structure assertions
- DTE-band edge cases and tie-breaking
- Delta-match accuracy + smile-aware uses contract's own IV
- Liquidity filter edge cases
- Hypothesis property tests for bounded outputs
"""

from __future__ import annotations

from datetime import date

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from engine.greeks import delta as greeks_delta
from engine.recommendation import Action, EmittedAction
from engine.strike_selector import (
    DTE_MAX_DAYS,
    DTE_MIN_DAYS,
    LegSide,
    StrikeSelection,
    select_strikes,
)
from engine.types import ChainSnapshot, OptionContract, OptionType

# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------


_ASOF = date(2026, 5, 11)
_EXPIRY_30 = date(2026, 6, 10)  # 30 DTE
_EXPIRY_60 = date(2026, 7, 10)  # 60 DTE
_EXPIRY_90 = date(2026, 8, 9)  # 90 DTE


def _contract(
    *,
    strike: float,
    option_type: OptionType,
    iv: float | None = 0.30,
    oi: int = 1000,
    volume: int = 500,
    bid: float | None = 1.0,
    ask: float | None = 1.1,
    mid: float | None = 1.05,
    expiry: date = _EXPIRY_30,
) -> OptionContract:
    return OptionContract(
        underlying="MSFT",
        expiry=expiry,
        strike=strike,
        option_type=option_type,
        iv=iv,
        open_interest=oi,
        volume=volume,
        bid=bid,
        ask=ask,
        mid=mid,
    )


def _chain(
    *,
    spot: float = 100.0,
    contracts: list[OptionContract] | None = None,
    as_of: date = _ASOF,
) -> ChainSnapshot:
    return ChainSnapshot(
        underlying="MSFT",
        spot=spot,
        as_of=as_of,
        contracts=tuple(contracts or []),
    )


def _full_chain(spot: float = 100.0) -> ChainSnapshot:
    """A balanced multi-expiry chain with a wide strike grid."""
    contracts: list[OptionContract] = []
    call_strikes = [95.0, 100.0, 105.0, 110.0, 115.0, 120.0, 125.0, 130.0]
    put_strikes = [70.0, 75.0, 80.0, 85.0, 90.0, 95.0, 100.0, 105.0]
    for exp in (_EXPIRY_30, _EXPIRY_60, _EXPIRY_90):
        for k in call_strikes:
            contracts.append(_contract(strike=k, option_type=OptionType.CALL, expiry=exp))
        for k in put_strikes:
            contracts.append(_contract(strike=k, option_type=OptionType.PUT, expiry=exp))
    return _chain(spot=spot, contracts=contracts)


def _action(
    *,
    emit: EmittedAction,
    target_dte: float = 30.0,
    target_delta: float = 0.25,
) -> Action:
    return Action(
        emit=emit,
        parameters={
            "target_dte": target_dte,
            "target_delta": target_delta,
            "size_pct": 0.50,
            "urgency_days": 5.0,
        },
    )


# ----------------------------------------------------------------------
# Per-emit leg-structure
# ----------------------------------------------------------------------


def test_sell_covered_call_partial_produces_short_call() -> None:
    sel = select_strikes(
        action=_action(emit=EmittedAction.SELL_COVERED_CALL_PARTIAL),
        chain_snapshot=_full_chain(),
    )
    assert len(sel.legs) == 1
    leg = sel.legs[0]
    assert leg.side is LegSide.SHORT
    assert leg.contract.option_type is OptionType.CALL
    assert sel.skipped_reason is None


def test_roll_up_and_out_produces_short_call() -> None:
    sel = select_strikes(
        action=_action(emit=EmittedAction.ROLL_UP_AND_OUT, target_dte=45.0),
        chain_snapshot=_full_chain(),
    )
    assert len(sel.legs) == 1
    assert sel.legs[0].side is LegSide.SHORT
    assert sel.legs[0].contract.option_type is OptionType.CALL


def test_wheel_short_put_produces_short_put() -> None:
    sel = select_strikes(
        action=_action(emit=EmittedAction.WHEEL_SHORT_PUT),
        chain_snapshot=_full_chain(),
    )
    assert len(sel.legs) == 1
    assert sel.legs[0].side is LegSide.SHORT
    assert sel.legs[0].contract.option_type is OptionType.PUT


def test_buy_long_dated_put_produces_long_put() -> None:
    sel = select_strikes(
        action=_action(emit=EmittedAction.BUY_LONG_DATED_PUT, target_dte=90.0),
        chain_snapshot=_full_chain(),
    )
    assert len(sel.legs) == 1
    assert sel.legs[0].side is LegSide.LONG
    assert sel.legs[0].contract.option_type is OptionType.PUT


def test_open_collar_produces_two_legs_short_call_then_long_put() -> None:
    sel = select_strikes(
        action=_action(emit=EmittedAction.OPEN_COLLAR, target_dte=45.0),
        chain_snapshot=_full_chain(),
    )
    assert len(sel.legs) == 2
    assert sel.legs[0].side is LegSide.SHORT
    assert sel.legs[0].contract.option_type is OptionType.CALL
    assert sel.legs[1].side is LegSide.LONG
    assert sel.legs[1].contract.option_type is OptionType.PUT


@pytest.mark.parametrize(
    "emit",
    [
        EmittedAction.REDUCE_COVERAGE,
        EmittedAction.MONETIZE_PUT,
        EmittedAction.NO_OP,
    ],
)
def test_close_existing_emits_skip_with_reason(emit: EmittedAction) -> None:
    sel = select_strikes(
        action=_action(emit=emit),
        chain_snapshot=_full_chain(),
    )
    assert sel.legs == ()
    assert sel.skipped_reason is not None
    assert "no concrete strike selection" in sel.skipped_reason


def test_strike_selection_echoes_emit() -> None:
    sel = select_strikes(
        action=_action(emit=EmittedAction.OPEN_COLLAR),
        chain_snapshot=_full_chain(),
    )
    assert sel.emit is EmittedAction.OPEN_COLLAR


# ----------------------------------------------------------------------
# DTE matching
# ----------------------------------------------------------------------


def test_dte_picks_closest_expiry() -> None:
    sel = select_strikes(
        action=_action(emit=EmittedAction.SELL_COVERED_CALL_PARTIAL, target_dte=45.0),
        chain_snapshot=_full_chain(),
    )
    # 30 + 60 are equidistant from 45; tie-break favors smaller DTE
    assert sel.legs[0].dte_actual == 30


def test_dte_picks_exact_match_when_available() -> None:
    sel = select_strikes(
        action=_action(emit=EmittedAction.SELL_COVERED_CALL_PARTIAL, target_dte=60.0),
        chain_snapshot=_full_chain(),
    )
    assert sel.legs[0].dte_actual == 60


def test_dte_band_floor_excludes_short_dte() -> None:
    short = date(2026, 5, 14)  # 3 DTE — below floor
    contracts = [
        _contract(strike=105.0, option_type=OptionType.CALL, expiry=short),
        _contract(strike=110.0, option_type=OptionType.CALL, expiry=short),
    ]
    sel = select_strikes(
        action=_action(emit=EmittedAction.SELL_COVERED_CALL_PARTIAL, target_dte=5.0),
        chain_snapshot=_chain(contracts=contracts),
    )
    assert sel.legs == ()
    assert "DTE band" in (sel.skipped_reason or "")


def test_dte_band_ceiling_excludes_leaps() -> None:
    leap = date(2027, 12, 17)
    contracts = [_contract(strike=105.0, option_type=OptionType.CALL, expiry=leap)]
    sel = select_strikes(
        action=_action(emit=EmittedAction.SELL_COVERED_CALL_PARTIAL, target_dte=400.0),
        chain_snapshot=_chain(contracts=contracts),
    )
    assert sel.legs == ()
    assert "DTE band" in (sel.skipped_reason or "")


def test_dte_band_constants() -> None:
    assert DTE_MIN_DAYS == 7
    assert DTE_MAX_DAYS == 365


# ----------------------------------------------------------------------
# Delta matching
# ----------------------------------------------------------------------


def test_delta_match_picks_nearest_strike() -> None:
    sel = select_strikes(
        action=_action(
            emit=EmittedAction.SELL_COVERED_CALL_PARTIAL,
            target_dte=30.0,
            target_delta=0.25,
        ),
        chain_snapshot=_full_chain(),
    )
    leg = sel.legs[0]
    assert leg.delta_distance < 0.10


def test_delta_match_call_returns_otm_strike() -> None:
    sel = select_strikes(
        action=_action(
            emit=EmittedAction.SELL_COVERED_CALL_PARTIAL, target_delta=0.25
        ),
        chain_snapshot=_full_chain(spot=100.0),
    )
    leg = sel.legs[0]
    assert leg.contract.strike > 100.0
    assert leg.delta_target > 0.0


def test_delta_match_put_returns_otm_strike() -> None:
    sel = select_strikes(
        action=_action(emit=EmittedAction.BUY_LONG_DATED_PUT, target_delta=0.25),
        chain_snapshot=_full_chain(spot=100.0),
    )
    leg = sel.legs[0]
    assert leg.contract.strike < 100.0
    assert leg.delta_target < 0.0


def test_delta_match_uses_contract_own_iv() -> None:
    contracts = [
        _contract(strike=105.0, option_type=OptionType.CALL, iv=0.20, expiry=_EXPIRY_30),
        _contract(strike=110.0, option_type=OptionType.CALL, iv=0.40, expiry=_EXPIRY_30),
        _contract(strike=115.0, option_type=OptionType.CALL, iv=0.30, expiry=_EXPIRY_30),
    ]
    snap = _chain(contracts=contracts)
    sel = select_strikes(
        action=_action(emit=EmittedAction.SELL_COVERED_CALL_PARTIAL),
        chain_snapshot=snap,
    )
    leg = sel.legs[0]
    expected_delta = greeks_delta(
        spot=100.0,
        strike=leg.contract.strike,
        tau=leg.dte_actual / 365.0,
        iv=leg.contract.iv,  # type: ignore[arg-type]
        r=0.05,
        q=0.0,
        option_type=OptionType.CALL,
    )
    assert leg.delta_actual == pytest.approx(expected_delta, abs=1e-9)


# ----------------------------------------------------------------------
# Liquidity filters
# ----------------------------------------------------------------------


def test_iv_none_filtered() -> None:
    contracts = [
        _contract(strike=105.0, option_type=OptionType.CALL, iv=None),
        _contract(strike=110.0, option_type=OptionType.CALL, iv=0.30),
    ]
    sel = select_strikes(
        action=_action(emit=EmittedAction.SELL_COVERED_CALL_PARTIAL),
        chain_snapshot=_chain(contracts=contracts),
    )
    assert len(sel.legs) == 1
    assert sel.legs[0].contract.strike == 110.0


def test_iv_zero_filtered() -> None:
    contracts = [
        _contract(strike=105.0, option_type=OptionType.CALL, iv=0.0),
        _contract(strike=110.0, option_type=OptionType.CALL, iv=0.30),
    ]
    sel = select_strikes(
        action=_action(emit=EmittedAction.SELL_COVERED_CALL_PARTIAL),
        chain_snapshot=_chain(contracts=contracts),
    )
    assert len(sel.legs) == 1
    assert sel.legs[0].contract.strike == 110.0


def test_zero_oi_filtered() -> None:
    contracts = [
        _contract(strike=105.0, option_type=OptionType.CALL, oi=0),
        _contract(strike=110.0, option_type=OptionType.CALL, oi=500),
    ]
    sel = select_strikes(
        action=_action(emit=EmittedAction.SELL_COVERED_CALL_PARTIAL),
        chain_snapshot=_chain(contracts=contracts),
    )
    assert len(sel.legs) == 1
    assert sel.legs[0].contract.strike == 110.0


def test_missing_quote_filtered() -> None:
    contracts = [
        _contract(strike=105.0, option_type=OptionType.CALL, bid=None, ask=None),
        _contract(strike=110.0, option_type=OptionType.CALL, bid=1.0, ask=1.1),
    ]
    sel = select_strikes(
        action=_action(emit=EmittedAction.SELL_COVERED_CALL_PARTIAL),
        chain_snapshot=_chain(contracts=contracts),
    )
    assert len(sel.legs) == 1
    assert sel.legs[0].contract.strike == 110.0


def test_inverted_quote_filtered() -> None:
    contracts = [
        _contract(strike=105.0, option_type=OptionType.CALL, bid=1.5, ask=1.0),
        _contract(strike=110.0, option_type=OptionType.CALL, bid=1.0, ask=1.1),
    ]
    sel = select_strikes(
        action=_action(emit=EmittedAction.SELL_COVERED_CALL_PARTIAL),
        chain_snapshot=_chain(contracts=contracts),
    )
    assert len(sel.legs) == 1
    assert sel.legs[0].contract.strike == 110.0


def test_no_eligible_contracts_yields_skipped_reason() -> None:
    contracts = [
        _contract(strike=105.0, option_type=OptionType.CALL, iv=None),
        _contract(strike=110.0, option_type=OptionType.CALL, oi=0),
    ]
    sel = select_strikes(
        action=_action(emit=EmittedAction.SELL_COVERED_CALL_PARTIAL),
        chain_snapshot=_chain(contracts=contracts),
    )
    assert sel.legs == ()
    assert "No eligible CALL contracts" in (sel.skipped_reason or "")


def test_no_put_contracts_for_long_put_yields_skipped_reason() -> None:
    contracts = [
        _contract(strike=k, option_type=OptionType.CALL, expiry=_EXPIRY_30)
        for k in (105.0, 110.0, 115.0)
    ]
    sel = select_strikes(
        action=_action(emit=EmittedAction.BUY_LONG_DATED_PUT, target_dte=30.0),
        chain_snapshot=_chain(contracts=contracts),
    )
    assert sel.legs == ()
    assert "No eligible PUT contracts" in (sel.skipped_reason or "")


def test_collar_skips_if_either_leg_unselectable() -> None:
    contracts = [
        _contract(strike=k, option_type=OptionType.CALL, expiry=_EXPIRY_30)
        for k in (105.0, 110.0, 115.0)
    ]
    sel = select_strikes(
        action=_action(emit=EmittedAction.OPEN_COLLAR, target_dte=30.0),
        chain_snapshot=_chain(contracts=contracts),
    )
    assert sel.legs == ()
    assert sel.skipped_reason is not None


# ----------------------------------------------------------------------
# Mid price
# ----------------------------------------------------------------------


def test_mid_uses_contract_mid_when_present() -> None:
    contracts = [
        _contract(strike=105.0, option_type=OptionType.CALL, bid=1.0, ask=1.2, mid=1.07),
    ]
    sel = select_strikes(
        action=_action(emit=EmittedAction.SELL_COVERED_CALL_PARTIAL),
        chain_snapshot=_chain(contracts=contracts),
    )
    assert sel.legs[0].mid_price == 1.07


def test_mid_falls_back_to_bid_ask_average() -> None:
    contracts = [
        _contract(strike=105.0, option_type=OptionType.CALL, bid=1.0, ask=1.2, mid=None),
    ]
    sel = select_strikes(
        action=_action(emit=EmittedAction.SELL_COVERED_CALL_PARTIAL),
        chain_snapshot=_chain(contracts=contracts),
    )
    assert sel.legs[0].mid_price == pytest.approx(1.10, abs=1e-12)


# ----------------------------------------------------------------------
# Missing parameters
# ----------------------------------------------------------------------


def test_missing_target_dte_in_parameters() -> None:
    bad = Action(
        emit=EmittedAction.SELL_COVERED_CALL_PARTIAL,
        parameters={"target_delta": 0.25},  # missing target_dte
    )
    sel = select_strikes(action=bad, chain_snapshot=_full_chain())
    assert sel.legs == ()
    assert "missing target_dte" in (sel.skipped_reason or "")


def test_missing_target_delta_in_parameters() -> None:
    bad = Action(
        emit=EmittedAction.SELL_COVERED_CALL_PARTIAL,
        parameters={"target_dte": 30.0},  # missing target_delta
    )
    sel = select_strikes(action=bad, chain_snapshot=_full_chain())
    assert sel.legs == ()
    assert "missing target_dte or target_delta" in (sel.skipped_reason or "")


# ----------------------------------------------------------------------
# Shape + determinism
# ----------------------------------------------------------------------


def test_select_strikes_returns_strike_selection() -> None:
    sel = select_strikes(
        action=_action(emit=EmittedAction.SELL_COVERED_CALL_PARTIAL),
        chain_snapshot=_full_chain(),
    )
    assert isinstance(sel, StrikeSelection)
    assert isinstance(sel.legs, tuple)


def test_select_strikes_is_deterministic() -> None:
    snap = _full_chain()
    a = select_strikes(action=_action(emit=EmittedAction.OPEN_COLLAR, target_dte=45.0), chain_snapshot=snap)
    b = select_strikes(action=_action(emit=EmittedAction.OPEN_COLLAR, target_dte=45.0), chain_snapshot=snap)
    assert a == b


def test_strike_selection_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    sel = select_strikes(
        action=_action(emit=EmittedAction.SELL_COVERED_CALL_PARTIAL),
        chain_snapshot=_full_chain(),
    )
    with pytest.raises(FrozenInstanceError):
        sel.skipped_reason = "x"  # type: ignore[misc]


def test_strike_leg_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    sel = select_strikes(
        action=_action(emit=EmittedAction.SELL_COVERED_CALL_PARTIAL),
        chain_snapshot=_full_chain(),
    )
    leg = sel.legs[0]
    with pytest.raises(FrozenInstanceError):
        leg.delta_target = 0.0  # type: ignore[misc]


# ----------------------------------------------------------------------
# Hypothesis property tests
# ----------------------------------------------------------------------


@given(
    target_delta=st.floats(min_value=0.05, max_value=0.95),
    target_dte=st.sampled_from([14.0, 30.0, 45.0, 60.0, 90.0]),
)
@settings(max_examples=30, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_call_leg_delta_distance_bounded(
    target_delta: float, target_dte: float
) -> None:
    sel = select_strikes(
        action=_action(
            emit=EmittedAction.SELL_COVERED_CALL_PARTIAL,
            target_delta=target_delta,
            target_dte=target_dte,
        ),
        chain_snapshot=_full_chain(),
    )
    if sel.legs:
        leg = sel.legs[0]
        assert leg.delta_distance < 0.5


@given(emit=st.sampled_from(list(EmittedAction)))
@settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_emit_echoed_through(emit: EmittedAction) -> None:
    sel = select_strikes(action=_action(emit=emit), chain_snapshot=_full_chain())
    assert sel.emit is emit


@given(
    emit=st.sampled_from(
        [
            EmittedAction.SELL_COVERED_CALL_PARTIAL,
            EmittedAction.BUY_LONG_DATED_PUT,
            EmittedAction.OPEN_COLLAR,
            EmittedAction.WHEEL_SHORT_PUT,
        ]
    ),
)
@settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_leg_dte_within_band(emit: EmittedAction) -> None:
    sel = select_strikes(
        action=_action(emit=emit, target_dte=45.0),
        chain_snapshot=_full_chain(),
    )
    for leg in sel.legs:
        assert DTE_MIN_DAYS <= leg.dte_actual <= DTE_MAX_DAYS
