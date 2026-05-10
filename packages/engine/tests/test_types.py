"""ChainSnapshot + OptionContract validation + immutability tests."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from engine.types import ChainSnapshot, OptionContract, OptionType


def _contract(**overrides: object) -> OptionContract:
    base: dict[str, object] = {
        "underlying": "MSFT",
        "expiry": date(2026, 6, 19),
        "strike": 420.0,
        "option_type": OptionType.CALL,
        "mid": 8.50,
        "bid": 8.45,
        "ask": 8.55,
        "iv": 0.32,
        "open_interest": 1500,
        "volume": 200,
    }
    base.update(overrides)
    return OptionContract(**base)  # type: ignore[arg-type]


def test_contract_constructs() -> None:
    c = _contract()
    assert c.underlying == "MSFT"
    assert c.option_type is OptionType.CALL
    assert c.iv == 0.32


def test_contract_is_frozen() -> None:
    c = _contract()
    with pytest.raises(ValidationError):
        c.strike = 999.0  # type: ignore[misc]


def test_strike_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        _contract(strike=0.0)
    with pytest.raises(ValidationError):
        _contract(strike=-1.0)


def test_iv_lower_bound() -> None:
    with pytest.raises(ValidationError):
        _contract(iv=-0.01)
    # IV > 1 is unusual but legal (event extremes).
    assert _contract(iv=1.5).iv == 1.5


def test_open_interest_and_volume_nonnegative() -> None:
    with pytest.raises(ValidationError):
        _contract(open_interest=-1)
    with pytest.raises(ValidationError):
        _contract(volume=-1)


def test_chain_snapshot_constructs_empty() -> None:
    snap = ChainSnapshot(
        underlying="MSFT",
        spot=415.50,
        as_of=date(2026, 5, 9),
        contracts=(),
    )
    assert snap.contracts == ()


def test_chain_snapshot_constructs_with_contracts() -> None:
    snap = ChainSnapshot(
        underlying="MSFT",
        spot=415.50,
        as_of=date(2026, 5, 9),
        contracts=(_contract(), _contract(option_type=OptionType.PUT, strike=410.0)),
    )
    assert len(snap.contracts) == 2
    assert snap.contracts[1].option_type is OptionType.PUT


def test_chain_snapshot_spot_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        ChainSnapshot(underlying="MSFT", spot=0.0, as_of=date(2026, 5, 9), contracts=())


def test_chain_snapshot_is_frozen() -> None:
    snap = ChainSnapshot(
        underlying="MSFT", spot=415.50, as_of=date(2026, 5, 9), contracts=()
    )
    with pytest.raises(ValidationError):
        snap.spot = 999.99  # type: ignore[misc]
