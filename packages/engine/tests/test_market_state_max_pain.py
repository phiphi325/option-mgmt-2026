"""Max-pain primitive tests (M1.2)."""

from __future__ import annotations

from datetime import date

import pytest

from engine.market_state import compute_max_pain
from engine.market_state.max_pain import CONTRACT_MULTIPLIER
from engine.types import OptionContract, OptionType

EXPIRY = date(2026, 6, 19)


def _contract(
    *,
    strike: float,
    option_type: OptionType,
    open_interest: int,
    expiry: date = EXPIRY,
) -> OptionContract:
    """Test helper: build an OptionContract with sensible defaults."""
    return OptionContract(
        underlying="MSFT",
        expiry=expiry,
        strike=strike,
        option_type=option_type,
        # The pain calculation only reads open_interest + expiry + strike + type.
        # Everything below is filler to satisfy Pydantic validation.
        mid=1.0,
        bid=0.95,
        ask=1.05,
        iv=0.25,
        open_interest=open_interest,
        volume=0,
    )


# ----------------------------------------------------------------------
# happy paths
# ----------------------------------------------------------------------


def test_max_pain_symmetric_chain_pins_at_atm() -> None:
    """Equal call + put OI at the same strikes → max pain at the median strike."""
    strikes = [95.0, 100.0, 105.0]
    contracts = []
    for k in strikes:
        contracts.append(_contract(strike=k, option_type=OptionType.CALL, open_interest=100))
        contracts.append(_contract(strike=k, option_type=OptionType.PUT, open_interest=100))
    assert compute_max_pain(contracts=contracts, expiry=EXPIRY) == 100.0


def test_max_pain_hand_computed_three_strikes() -> None:
    """Hand-computed example exercises the actual minimization.

    Strikes: 95, 100, 105
    Calls (OI):  95→100, 100→200, 105→100
    Puts  (OI):  95→ 50, 100→200, 105→ 50

    pain_at(95):
      call_pain = 100*max(95-95,0) + 200*max(95-100,0) + 100*max(95-105,0) = 0
      put_pain  = 50 *max(95-95,0) + 200*max(100-95,0) + 50 *max(105-95,0)
                = 0 + 1000 + 500 = 1500
      total = 1500 * 100 = 150,000

    pain_at(100):
      call_pain = 100*5 + 200*0 + 100*0 = 500
      put_pain  = 50 *0 + 200*0 + 50 *5 = 250
      total = (500 + 250) * 100 = 75,000

    pain_at(105):
      call_pain = 100*10 + 200*5 + 100*0 = 2000
      put_pain  = 50 *0  + 200*0 + 50 *0 = 0
      total = 2000 * 100 = 200,000

    min is 100. Max pain = 100.
    """
    contracts = [
        _contract(strike=95.0, option_type=OptionType.CALL, open_interest=100),
        _contract(strike=100.0, option_type=OptionType.CALL, open_interest=200),
        _contract(strike=105.0, option_type=OptionType.CALL, open_interest=100),
        _contract(strike=95.0, option_type=OptionType.PUT, open_interest=50),
        _contract(strike=100.0, option_type=OptionType.PUT, open_interest=200),
        _contract(strike=105.0, option_type=OptionType.PUT, open_interest=50),
    ]
    assert compute_max_pain(contracts=contracts, expiry=EXPIRY) == 100.0


def test_max_pain_skewed_call_heavy() -> None:
    """Heavy call OI above spot → max pain pulls toward the call concentration.

    All call OI at 110, no puts. Pain at strike K = call_pain_only:
      pain_at(95)  = 200 * max(95-110,0)  = 0   (best — calls all OTM)
      pain_at(100) = 200 * max(100-110,0) = 0   (tied)
      pain_at(105) = 200 * max(105-110,0) = 0   (tied)
      pain_at(110) = 200 * max(110-110,0) = 0   (tied — boundary)
      pain_at(115) = 200 * max(115-110,0) = 1000 * 100 = 100,000

    With ties at the bottom, Python's `min(... key=...)` returns the
    first matching element — i.e. the lowest strike where call_pain = 0.
    """
    contracts = [
        _contract(strike=95.0, option_type=OptionType.CALL, open_interest=10),
        _contract(strike=100.0, option_type=OptionType.CALL, open_interest=10),
        _contract(strike=110.0, option_type=OptionType.CALL, open_interest=200),
        _contract(strike=115.0, option_type=OptionType.CALL, open_interest=10),
    ]
    result = compute_max_pain(contracts=contracts, expiry=EXPIRY)
    # All strikes <= 110 have zero pain (no puts, calls are ATM/OTM at those strikes).
    # Lowest tied strike wins → 95.
    assert result == 95.0


def test_max_pain_single_strike() -> None:
    """One strike present → that strike (vacuously the minimum)."""
    contracts = [
        _contract(strike=100.0, option_type=OptionType.CALL, open_interest=50),
        _contract(strike=100.0, option_type=OptionType.PUT, open_interest=50),
    ]
    assert compute_max_pain(contracts=contracts, expiry=EXPIRY) == 100.0


def test_max_pain_filters_other_expiries() -> None:
    """Contracts at other expiries are ignored."""
    other_expiry = date(2026, 7, 17)
    target = [
        _contract(strike=100.0, option_type=OptionType.CALL, open_interest=100),
        _contract(strike=100.0, option_type=OptionType.PUT, open_interest=100),
    ]
    distractors = [
        _contract(strike=200.0, option_type=OptionType.CALL, open_interest=10000, expiry=other_expiry),
        _contract(strike=50.0, option_type=OptionType.PUT, open_interest=10000, expiry=other_expiry),
    ]
    assert compute_max_pain(contracts=target + distractors, expiry=EXPIRY) == 100.0


# ----------------------------------------------------------------------
# edge cases
# ----------------------------------------------------------------------


def test_max_pain_no_matching_expiry_raises() -> None:
    other_expiry = date(2026, 7, 17)
    contracts = [
        _contract(strike=100.0, option_type=OptionType.CALL, open_interest=10, expiry=other_expiry),
    ]
    with pytest.raises(ValueError, match="no contracts"):
        compute_max_pain(contracts=contracts, expiry=EXPIRY)


def test_max_pain_empty_contracts_raises() -> None:
    with pytest.raises(ValueError, match="no contracts"):
        compute_max_pain(contracts=[], expiry=EXPIRY)


def test_max_pain_zero_oi_strikes_dont_distort() -> None:
    """Zero-OI strikes contribute zero pain at any K — should not move the answer."""
    contracts = [
        _contract(strike=95.0, option_type=OptionType.CALL, open_interest=0),
        _contract(strike=100.0, option_type=OptionType.CALL, open_interest=100),
        _contract(strike=100.0, option_type=OptionType.PUT, open_interest=100),
        _contract(strike=999.0, option_type=OptionType.PUT, open_interest=0),
    ]
    assert compute_max_pain(contracts=contracts, expiry=EXPIRY) == 100.0


# ----------------------------------------------------------------------
# constants
# ----------------------------------------------------------------------


def test_contract_multiplier_is_100() -> None:
    """Sanity check on the constant — US equity-option convention."""
    assert CONTRACT_MULTIPLIER == 100
