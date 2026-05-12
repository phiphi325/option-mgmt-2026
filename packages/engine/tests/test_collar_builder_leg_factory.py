"""Unit tests for `engine.collar_builder.leg_factory`."""

from __future__ import annotations

from datetime import date

import pytest

from engine.collar_builder.leg_factory import make_long_put, make_short_call
from engine.types import OptionContract, OptionType


def _put(strike: float, bid: float, ask: float) -> OptionContract:
    return OptionContract(
        underlying="MSFT",
        expiry=date(2026, 6, 19),
        strike=strike,
        option_type=OptionType.PUT,
        bid=bid,
        ask=ask,
        iv=0.30,
        open_interest=1000,
        volume=200,
    )


def _call(strike: float, bid: float, ask: float) -> OptionContract:
    return OptionContract(
        underlying="MSFT",
        expiry=date(2026, 6, 19),
        strike=strike,
        option_type=OptionType.CALL,
        bid=bid,
        ask=ask,
        iv=0.30,
        open_interest=1000,
        volume=200,
    )


class TestMakeLongPut:
    def test_basic_construction(self) -> None:
        leg = make_long_put(_put(390.0, 2.00, 2.20), qty=1, delta=-0.25)
        assert leg.kind == "PUT"
        assert leg.side == "BUY"
        assert leg.strike == 390.0
        assert leg.qty == 1

    def test_premium_is_positive_paid(self) -> None:
        """Long put = BUY → premium is positive (debit paid)."""
        leg = make_long_put(_put(390.0, 2.00, 2.20), qty=1, delta=-0.25)
        assert leg.premium > 0
        assert leg.premium == pytest.approx(2.10)  # mid of 2.00 and 2.20

    def test_mid_from_bid_ask(self) -> None:
        leg = make_long_put(_put(390.0, 1.00, 3.00), qty=1, delta=-0.25)
        assert leg.mid == pytest.approx(2.00)

    def test_delta_is_signed_negative_for_put(self) -> None:
        """PUT delta must be in [-1, 0) regardless of input sign."""
        leg_signed = make_long_put(_put(390.0, 2.0, 2.0), qty=1, delta=-0.25)
        leg_unsigned = make_long_put(_put(390.0, 2.0, 2.0), qty=1, delta=0.25)
        assert leg_signed.delta == -0.25
        assert leg_unsigned.delta == -0.25  # normalized to signed

    def test_raises_on_wrong_option_type(self) -> None:
        with pytest.raises(ValueError, match="requires a PUT"):
            make_long_put(_call(410.0, 2.0, 2.2), qty=1, delta=-0.25)

    def test_raises_on_non_positive_qty(self) -> None:
        with pytest.raises(ValueError, match="qty must be positive"):
            make_long_put(_put(390.0, 2.0, 2.2), qty=0, delta=-0.25)


class TestMakeShortCall:
    def test_basic_construction(self) -> None:
        leg = make_short_call(_call(420.0, 1.80, 2.00), qty=1, delta=0.25)
        assert leg.kind == "CALL"
        assert leg.side == "SELL"
        assert leg.strike == 420.0

    def test_premium_is_negative_received(self) -> None:
        """Short call = SELL → premium is negative (credit received)."""
        leg = make_short_call(_call(420.0, 1.80, 2.00), qty=1, delta=0.25)
        assert leg.premium < 0
        assert leg.premium == pytest.approx(-1.90)

    def test_delta_is_signed_positive_for_call(self) -> None:
        leg_signed = make_short_call(_call(420.0, 1.8, 2.0), qty=1, delta=0.25)
        leg_neg = make_short_call(_call(420.0, 1.8, 2.0), qty=1, delta=-0.25)
        assert leg_signed.delta == 0.25
        assert leg_neg.delta == 0.25  # normalized to positive

    def test_raises_on_wrong_option_type(self) -> None:
        with pytest.raises(ValueError, match="requires a CALL"):
            make_short_call(_put(390.0, 2.0, 2.2), qty=1, delta=0.25)
