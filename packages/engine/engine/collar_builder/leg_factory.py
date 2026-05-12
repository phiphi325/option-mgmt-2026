"""Convert `OptionContract` chain quotes into typed `CollarLeg` instances.

Pure helpers — no engine state, no I/O. Used by `structures.py` solvers
to build leg pairs and by tests to construct deterministic fixtures.

Sign conventions (see `types.CollarLeg` docstring for full detail):

  delta:    Echoed from the contract directly — calls in (0, 1], puts
            in [-1, 0). Some chain feeds publish unsigned put deltas;
            this module accepts both and normalizes to signed.
  premium:  Signed by `side` — BUY = +mid (paid), SELL = -mid (received).
"""

from __future__ import annotations

from engine.types import OptionContract, OptionType

from .types import CollarLeg


def _normalize_delta(contract: OptionContract, raw_delta: float | None) -> float:
    """Return a signed delta from an `OptionContract`.

    If the contract has no `iv` data this function returns 0.0 — the
    caller should filter out such contracts before calling, but we
    don't raise so the function stays composable.

    Calls are kept in (0, 1]; puts are forced to [-1, 0) by sign flip
    if the chain feed published an unsigned value.
    """
    if raw_delta is None:
        return 0.0
    if contract.option_type is OptionType.CALL:
        return abs(raw_delta)
    # PUT
    return -abs(raw_delta)


def _mid(contract: OptionContract) -> float:
    """Compute mid-price from bid/ask, falling back to the contract's
    `mid` field, falling back to 0.0 (which the solver treats as
    'no liquidity → skip')."""
    if contract.bid is not None and contract.ask is not None:
        return (contract.bid + contract.ask) / 2.0
    if contract.mid is not None:
        return contract.mid
    return 0.0


def make_long_put(
    contract: OptionContract,
    qty: int,
    *,
    delta: float | None = None,
) -> CollarLeg:
    """Build a BUY-PUT leg from a chain contract.

    Premium is positive (debit paid). Caller passes the explicit
    `delta` if the chain doesn't publish it (e.g., when the M1.6
    Greeks module computes it from IV + Black-Scholes).
    """
    if contract.option_type is not OptionType.PUT:
        raise ValueError(
            f"make_long_put requires a PUT contract; got {contract.option_type}"
        )
    if qty <= 0:
        raise ValueError(f"qty must be positive; got {qty}")
    mid = _mid(contract)
    return CollarLeg(
        kind="PUT",
        side="BUY",
        strike=contract.strike,
        expiry=contract.expiry,
        qty=qty,
        delta=_normalize_delta(contract, delta),
        iv=contract.iv or 0.0,
        bid=contract.bid or 0.0,
        ask=contract.ask or 0.0,
        mid=mid,
        premium=+mid,  # BUY: paid (positive)
    )


def make_short_call(
    contract: OptionContract,
    qty: int,
    *,
    delta: float | None = None,
) -> CollarLeg:
    """Build a SELL-CALL leg from a chain contract.

    Premium is negative (credit received).
    """
    if contract.option_type is not OptionType.CALL:
        raise ValueError(
            f"make_short_call requires a CALL contract; got {contract.option_type}"
        )
    if qty <= 0:
        raise ValueError(f"qty must be positive; got {qty}")
    mid = _mid(contract)
    return CollarLeg(
        kind="CALL",
        side="SELL",
        strike=contract.strike,
        expiry=contract.expiry,
        qty=qty,
        delta=_normalize_delta(contract, delta),
        iv=contract.iv or 0.0,
        bid=contract.bid or 0.0,
        ask=contract.ask or 0.0,
        mid=mid,
        premium=-mid,  # SELL: received (negative)
    )
