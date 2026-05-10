"""Put/Call Ratio primitive tests (M1.2)."""

from __future__ import annotations

from datetime import date

from engine.market_state import pcr_oi, pcr_volume
from engine.types import OptionContract, OptionType

EXPIRY = date(2026, 6, 19)


def _contract(
    *,
    option_type: OptionType,
    open_interest: int = 0,
    volume: int = 0,
    strike: float = 100.0,
    expiry: date = EXPIRY,
) -> OptionContract:
    return OptionContract(
        underlying="MSFT",
        expiry=expiry,
        strike=strike,
        option_type=option_type,
        mid=1.0,
        bid=0.95,
        ask=1.05,
        iv=0.25,
        open_interest=open_interest,
        volume=volume,
    )


# ----------------------------------------------------------------------
# pcr_volume
# ----------------------------------------------------------------------


def test_pcr_volume_balanced_returns_one() -> None:
    """Equal put and call volume → PCR = 1.0."""
    contracts = [
        _contract(option_type=OptionType.CALL, volume=100),
        _contract(option_type=OptionType.PUT, volume=100),
    ]
    assert pcr_volume(contracts=contracts) == 1.0


def test_pcr_volume_more_puts_above_one() -> None:
    contracts = [
        _contract(option_type=OptionType.CALL, volume=100),
        _contract(option_type=OptionType.PUT, volume=200),
    ]
    assert pcr_volume(contracts=contracts) == 2.0


def test_pcr_volume_more_calls_below_one() -> None:
    contracts = [
        _contract(option_type=OptionType.CALL, volume=200),
        _contract(option_type=OptionType.PUT, volume=50),
    ]
    assert pcr_volume(contracts=contracts) == 0.25


def test_pcr_volume_all_calls_returns_zero() -> None:
    """No put volume → PCR = 0.0 (numerator is 0)."""
    contracts = [
        _contract(option_type=OptionType.CALL, volume=500),
    ]
    assert pcr_volume(contracts=contracts) == 0.0


def test_pcr_volume_all_puts_returns_zero_degenerate() -> None:
    """No call volume → degenerate, returns 0.0 (sentinel: 'no signal')."""
    contracts = [
        _contract(option_type=OptionType.PUT, volume=500),
    ]
    assert pcr_volume(contracts=contracts) == 0.0


def test_pcr_volume_empty_returns_zero() -> None:
    assert pcr_volume(contracts=[]) == 0.0


def test_pcr_volume_aggregates_across_strikes_and_expiries() -> None:
    """No filtering — function sums whatever the caller passes."""
    other_expiry = date(2026, 7, 17)
    contracts = [
        _contract(option_type=OptionType.CALL, volume=50, strike=100.0),
        _contract(option_type=OptionType.CALL, volume=50, strike=110.0, expiry=other_expiry),
        _contract(option_type=OptionType.PUT, volume=80, strike=95.0),
        _contract(option_type=OptionType.PUT, volume=20, strike=90.0, expiry=other_expiry),
    ]
    # put_total=100, call_total=100, ratio=1.0
    assert pcr_volume(contracts=contracts) == 1.0


def test_pcr_volume_zero_open_interest_field_ignored() -> None:
    """pcr_volume reads .volume only, ignores .open_interest."""
    contracts = [
        _contract(option_type=OptionType.CALL, volume=100, open_interest=0),
        _contract(option_type=OptionType.PUT, volume=200, open_interest=99999),
    ]
    assert pcr_volume(contracts=contracts) == 2.0


# ----------------------------------------------------------------------
# pcr_oi
# ----------------------------------------------------------------------


def test_pcr_oi_balanced_returns_one() -> None:
    contracts = [
        _contract(option_type=OptionType.CALL, open_interest=500),
        _contract(option_type=OptionType.PUT, open_interest=500),
    ]
    assert pcr_oi(contracts=contracts) == 1.0


def test_pcr_oi_more_puts_above_one() -> None:
    contracts = [
        _contract(option_type=OptionType.CALL, open_interest=100),
        _contract(option_type=OptionType.PUT, open_interest=300),
    ]
    assert pcr_oi(contracts=contracts) == 3.0


def test_pcr_oi_all_calls_returns_zero() -> None:
    contracts = [
        _contract(option_type=OptionType.CALL, open_interest=1000),
    ]
    assert pcr_oi(contracts=contracts) == 0.0


def test_pcr_oi_all_puts_returns_zero_degenerate() -> None:
    contracts = [
        _contract(option_type=OptionType.PUT, open_interest=500),
    ]
    assert pcr_oi(contracts=contracts) == 0.0


def test_pcr_oi_empty_returns_zero() -> None:
    assert pcr_oi(contracts=[]) == 0.0


def test_pcr_oi_zero_volume_field_ignored() -> None:
    """pcr_oi reads .open_interest only, ignores .volume."""
    contracts = [
        _contract(option_type=OptionType.CALL, open_interest=100, volume=99999),
        _contract(option_type=OptionType.PUT, open_interest=300, volume=0),
    ]
    assert pcr_oi(contracts=contracts) == 3.0


def test_pcr_oi_and_pcr_volume_are_independent() -> None:
    """Ratios on different fields can disagree — that's the whole point.

    Heavy intraday volume but balanced positioning shows up as
    different pcr_volume vs pcr_oi.
    """
    contracts = [
        _contract(option_type=OptionType.CALL, open_interest=1000, volume=50),
        _contract(option_type=OptionType.PUT, open_interest=1000, volume=200),
    ]
    assert pcr_oi(contracts=contracts) == 1.0
    assert pcr_volume(contracts=contracts) == 4.0
