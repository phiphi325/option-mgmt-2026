"""25-delta IV skew primitive tests (M1.6).

Per plan v1.2 §17 M1.6 acceptance and §9.3 step 3.

The M1.5b stub returned 0 unconditionally. M1.6 replaces it with a real
BS-delta-based implementation. These tests verify:

  - Flat smile → 0 skew (the baseline)
  - Put-side rich → positive skew
  - Call-side rich → negative skew
  - Multi-expiry averaging
  - Edge cases (missing IV, only one side, empty focus, invalid spot)
  - The skew is computed *for each contract's own IV* (smile-aware)
"""

from __future__ import annotations

from datetime import date

import pytest

from engine.flow_score import skew_25d
from engine.types import ChainSnapshot, OptionContract, OptionType

# ----------------------------------------------------------------------
# helpers — build chains with controlled smile shapes
# ----------------------------------------------------------------------


_ASOF = date(2026, 5, 10)
_EXPIRY = date(2026, 6, 19)
_EXPIRY_FAR = date(2026, 12, 18)


def _c(
    *,
    strike: float,
    option_type: OptionType,
    iv: float,
    oi: int = 1000,
    volume: int = 100,
    expiry: date = _EXPIRY,
) -> OptionContract:
    return OptionContract(
        underlying="MSFT",
        expiry=expiry,
        strike=strike,
        option_type=option_type,
        open_interest=oi,
        volume=volume,
        iv=iv,
        mid=1.0,
        bid=0.95,
        ask=1.05,
    )


# ----------------------------------------------------------------------
# baseline — flat smile → 0 skew
# ----------------------------------------------------------------------


def test_skew_flat_smile_zero() -> None:
    """All contracts at IV=0.30 → 25-Δ put IV = 25-Δ call IV → skew = 0."""
    contracts: list[OptionContract] = []
    for k in [80.0, 90.0, 95.0, 100.0, 105.0, 110.0, 120.0]:
        contracts.append(_c(strike=k, option_type=OptionType.CALL, iv=0.30))
        contracts.append(_c(strike=k, option_type=OptionType.PUT, iv=0.30))
    s = skew_25d(
        contracts=contracts, expiry_focus=[_EXPIRY], spot=100.0, as_of=_ASOF
    )
    assert s == pytest.approx(0.0, abs=1e-12)


# ----------------------------------------------------------------------
# put-side rich → positive skew (bearish flow)
# ----------------------------------------------------------------------


def test_skew_put_side_rich_positive() -> None:
    """OTM puts have higher IV than OTM calls → skew > 0 (bearish)."""
    contracts: list[OptionContract] = []
    # Calls at IV=0.25 across strikes
    for k in [100.0, 105.0, 110.0, 120.0]:
        contracts.append(_c(strike=k, option_type=OptionType.CALL, iv=0.25))
    # Puts at IV=0.35 across strikes (richer)
    for k in [80.0, 90.0, 95.0, 100.0]:
        contracts.append(_c(strike=k, option_type=OptionType.PUT, iv=0.35))
    s = skew_25d(
        contracts=contracts, expiry_focus=[_EXPIRY], spot=100.0, as_of=_ASOF
    )
    # Skew should be the IV gap = 0.35 - 0.25 = 0.10
    assert s == pytest.approx(0.10, abs=1e-3)


# ----------------------------------------------------------------------
# call-side rich → negative skew (bullish flow)
# ----------------------------------------------------------------------


def test_skew_call_side_rich_negative() -> None:
    """OTM calls have higher IV than OTM puts → skew < 0 (bullish)."""
    contracts: list[OptionContract] = []
    for k in [100.0, 105.0, 110.0, 120.0]:
        contracts.append(_c(strike=k, option_type=OptionType.CALL, iv=0.40))
    for k in [80.0, 90.0, 95.0, 100.0]:
        contracts.append(_c(strike=k, option_type=OptionType.PUT, iv=0.25))
    s = skew_25d(
        contracts=contracts, expiry_focus=[_EXPIRY], spot=100.0, as_of=_ASOF
    )
    # 25-Δ put IV = 0.25, 25-Δ call IV = 0.40 → skew = -0.15
    assert s == pytest.approx(-0.15, abs=1e-3)


# ----------------------------------------------------------------------
# real smile shape (typical equity)
# ----------------------------------------------------------------------


def test_skew_typical_equity_smile() -> None:
    """Realistic skew: OTM put IV decreases linearly with strike (downward sloping put smile)."""
    contracts: list[OptionContract] = []
    # OTM puts: lower strikes → higher IV (typical "skew")
    contracts.append(_c(strike=80.0, option_type=OptionType.PUT, iv=0.42))
    contracts.append(_c(strike=85.0, option_type=OptionType.PUT, iv=0.38))
    contracts.append(_c(strike=90.0, option_type=OptionType.PUT, iv=0.34))
    contracts.append(_c(strike=95.0, option_type=OptionType.PUT, iv=0.32))
    contracts.append(_c(strike=100.0, option_type=OptionType.PUT, iv=0.30))
    # OTM calls: relatively flat
    contracts.append(_c(strike=100.0, option_type=OptionType.CALL, iv=0.28))
    contracts.append(_c(strike=105.0, option_type=OptionType.CALL, iv=0.27))
    contracts.append(_c(strike=110.0, option_type=OptionType.CALL, iv=0.26))
    contracts.append(_c(strike=120.0, option_type=OptionType.CALL, iv=0.25))
    s = skew_25d(
        contracts=contracts, expiry_focus=[_EXPIRY], spot=100.0, as_of=_ASOF
    )
    # 25-Δ put ≈ K=95 at IV=0.32; 25-Δ call ≈ K=105 at IV=0.27 → skew ≈ 0.05
    # Typical equity put-side fear premium.
    assert s == pytest.approx(0.05, abs=1e-3)


# ----------------------------------------------------------------------
# multi-expiry averaging
# ----------------------------------------------------------------------


def test_skew_multi_expiry_averages() -> None:
    """skew is the average across focus expiries."""
    contracts: list[OptionContract] = []
    # Near expiry: put-side richer (+0.10 skew)
    for k in [100.0, 110.0]:
        contracts.append(_c(strike=k, option_type=OptionType.CALL, iv=0.25))
    for k in [90.0, 100.0]:
        contracts.append(_c(strike=k, option_type=OptionType.PUT, iv=0.35))
    # Far expiry: more balanced (≈ 0 skew)
    for k in [100.0, 110.0]:
        contracts.append(
            _c(strike=k, option_type=OptionType.CALL, iv=0.30, expiry=_EXPIRY_FAR)
        )
    for k in [90.0, 100.0]:
        contracts.append(
            _c(strike=k, option_type=OptionType.PUT, iv=0.30, expiry=_EXPIRY_FAR)
        )
    s = skew_25d(
        contracts=contracts,
        expiry_focus=[_EXPIRY, _EXPIRY_FAR],
        spot=100.0,
        as_of=_ASOF,
    )
    # Average of +0.10 and 0.0 → 0.05
    assert s == pytest.approx(0.05, abs=1e-3)


# ----------------------------------------------------------------------
# missing IV / one-sided edge cases
# ----------------------------------------------------------------------


def test_skew_empty_focus_zero() -> None:
    """No focus expiries → 0."""
    contracts = [_c(strike=100.0, option_type=OptionType.CALL, iv=0.30)]
    assert (
        skew_25d(contracts=contracts, expiry_focus=[], spot=100.0, as_of=_ASOF)
        == 0.0
    )


def test_skew_no_puts_returns_zero() -> None:
    """An expiry with only calls is skipped → 0 (no qualifying expiry)."""
    contracts = [
        _c(strike=100.0, option_type=OptionType.CALL, iv=0.30),
        _c(strike=110.0, option_type=OptionType.CALL, iv=0.28),
    ]
    s = skew_25d(
        contracts=contracts, expiry_focus=[_EXPIRY], spot=100.0, as_of=_ASOF
    )
    assert s == 0.0


def test_skew_no_calls_returns_zero() -> None:
    contracts = [
        _c(strike=100.0, option_type=OptionType.PUT, iv=0.35),
        _c(strike=90.0, option_type=OptionType.PUT, iv=0.40),
    ]
    s = skew_25d(
        contracts=contracts, expiry_focus=[_EXPIRY], spot=100.0, as_of=_ASOF
    )
    assert s == 0.0


def test_skew_iv_none_filtered() -> None:
    """Contracts with iv=None are skipped (not usable for BS delta)."""
    contracts = [
        _c(strike=100.0, option_type=OptionType.CALL, iv=0.30),
        # Pydantic model allows iv=None; construct manually
        OptionContract(
            underlying="MSFT",
            expiry=_EXPIRY,
            strike=110.0,
            option_type=OptionType.CALL,
            open_interest=1000,
            volume=100,
            iv=None,
            mid=1.0,
            bid=0.95,
            ask=1.05,
        ),
        _c(strike=90.0, option_type=OptionType.PUT, iv=0.30),
    ]
    # Only two contracts have IV → 25-Δ call is K=100 (only choice), 25-Δ put is K=90 → skew = 0
    s = skew_25d(
        contracts=contracts, expiry_focus=[_EXPIRY], spot=100.0, as_of=_ASOF
    )
    assert s == pytest.approx(0.0, abs=1e-9)


def test_skew_iv_zero_filtered() -> None:
    """Contracts with iv=0 are skipped (BS delta undefined at iv=0)."""
    contracts = [
        _c(strike=100.0, option_type=OptionType.CALL, iv=0.30),
        # iv=0 contracts should be filtered
        _c(strike=110.0, option_type=OptionType.CALL, iv=0.0),
        _c(strike=90.0, option_type=OptionType.PUT, iv=0.30),
        _c(strike=85.0, option_type=OptionType.PUT, iv=0.0),
    ]
    s = skew_25d(
        contracts=contracts, expiry_focus=[_EXPIRY], spot=100.0, as_of=_ASOF
    )
    # Only IV=0.30 contracts survive → flat → 0
    assert s == pytest.approx(0.0, abs=1e-12)


# ----------------------------------------------------------------------
# validation
# ----------------------------------------------------------------------


def test_skew_rejects_nonpositive_spot() -> None:
    with pytest.raises(ValueError, match="spot must be > 0"):
        skew_25d(contracts=[], expiry_focus=[_EXPIRY], spot=0.0, as_of=_ASOF)
    with pytest.raises(ValueError, match="spot must be > 0"):
        skew_25d(contracts=[], expiry_focus=[_EXPIRY], spot=-100.0, as_of=_ASOF)


# ----------------------------------------------------------------------
# r and q overrides
# ----------------------------------------------------------------------


def test_skew_dividend_yield_override() -> None:
    """Passing a non-zero dividend yield changes the 25-delta strike selection.

    With high q, the e^(-qτ) factor shifts call deltas lower, so a call
    that was "above 25-delta" at q=0 may now be "below 25-delta" at q>0.
    Same chain, different q → potentially different 25-Δ strikes →
    potentially different skew.
    """
    contracts: list[OptionContract] = []
    # Slight smile so different strike selection yields different skew
    contracts.append(_c(strike=100.0, option_type=OptionType.CALL, iv=0.28))
    contracts.append(_c(strike=105.0, option_type=OptionType.CALL, iv=0.27))
    contracts.append(_c(strike=110.0, option_type=OptionType.CALL, iv=0.26))
    contracts.append(_c(strike=120.0, option_type=OptionType.CALL, iv=0.25))
    contracts.append(_c(strike=90.0, option_type=OptionType.PUT, iv=0.34))
    contracts.append(_c(strike=95.0, option_type=OptionType.PUT, iv=0.32))
    contracts.append(_c(strike=100.0, option_type=OptionType.PUT, iv=0.30))

    s_q0 = skew_25d(
        contracts=contracts,
        expiry_focus=[_EXPIRY],
        spot=100.0,
        as_of=_ASOF,
        dividend_yield=0.0,
    )
    s_q_high = skew_25d(
        contracts=contracts,
        expiry_focus=[_EXPIRY],
        spot=100.0,
        as_of=_ASOF,
        dividend_yield=0.10,
    )
    # Both should be valid (positive skew expected for this put-side-rich smile)
    assert s_q0 > 0.0
    assert s_q_high > 0.0


def test_skew_uses_chain_snapshot_when_compute_called() -> None:
    """Integration check: compute() passes spot + as_of from ChainSnapshot to skew_25d."""
    from engine.flow_score import compute

    contracts: list[OptionContract] = []
    # Strong put-side skew to verify it propagates
    for k in [100.0, 105.0, 110.0, 120.0]:
        contracts.append(_c(strike=k, option_type=OptionType.CALL, iv=0.20))
    for k in [80.0, 90.0, 95.0, 100.0]:
        contracts.append(_c(strike=k, option_type=OptionType.PUT, iv=0.40))
    snap = ChainSnapshot(
        underlying="MSFT", spot=100.0, as_of=_ASOF, contracts=tuple(contracts)
    )
    result = compute(chain_snapshot=snap, spot=100.0, expiry_focus=[_EXPIRY])
    # bearish_skew = max(0, +skew) and skew = 0.40 - 0.20 = 0.20 (clipped to 1.0)
    assert result.breakdown["bearish_skew"] == pytest.approx(0.20, abs=1e-3)
    assert result.breakdown["bullish_skew"] == 0.0
