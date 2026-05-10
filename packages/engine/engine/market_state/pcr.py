"""Put/Call Ratio primitives — volume and open interest.

Per plan v1.2 §9.1 (Market State Engine inputs `pcr_volume` and `pcr_oi`).

Two complementary signals:

  pcr_volume  Σ put_volume / Σ call_volume     short-term sentiment;
                                                noisy intraday but reactive.
  pcr_oi      Σ put_oi / Σ call_oi             structural positioning;
                                                slower-moving, more stable.

Higher PCR = more bearish positioning relative to calls. Both feed the
Market State Engine `classify()` (M1.4) and the Confidence Composer's
flow_alignment input.

Both functions sum across whatever contracts the caller passes — no
expiry/strike filtering. Callers pre-filter for the slice they want
("near-term contracts", "weekly chain", etc.).

Pure function (per ADR-0005). No I/O.

Degenerate cases:

  - Empty contracts list, or zero call total → returns 0.0. The function
    cannot divide by zero and there's no meaningful "infinity" value
    in a unit-interval-friendly downstream. Callers MUST treat 0.0 as
    "no signal / insufficient data" rather than "no puts" — distinguish
    via input validation if it matters.
"""

from __future__ import annotations

from collections.abc import Sequence

from engine.types import OptionContract, OptionType


def pcr_volume(*, contracts: Sequence[OptionContract]) -> float:
    """Put/Call ratio computed on contract volume.

    Args:
        contracts: Option contracts to aggregate. No filtering — caller
                   passes the slice they care about (full chain, weekly
                   chain, near-term chain, etc.).

    Returns:
        Σ put volume / Σ call volume. 0.0 if call volume is 0 (degenerate;
        treat as "no signal", not as a directional read).
    """
    put_total = 0
    call_total = 0
    for c in contracts:
        if c.option_type is OptionType.PUT:
            put_total += c.volume
        elif c.option_type is OptionType.CALL:
            call_total += c.volume
    if call_total == 0:
        return 0.0
    return put_total / call_total


def pcr_oi(*, contracts: Sequence[OptionContract]) -> float:
    """Put/Call ratio computed on open interest.

    Same semantics as `pcr_volume` but uses the slower-moving OI series.
    Less noisy intraday; better for "structural positioning" reads.

    Args:
        contracts: Option contracts to aggregate.

    Returns:
        Σ put OI / Σ call OI. 0.0 if call OI is 0 (degenerate).
    """
    put_total = 0
    call_total = 0
    for c in contracts:
        if c.option_type is OptionType.PUT:
            put_total += c.open_interest
        elif c.option_type is OptionType.CALL:
            call_total += c.open_interest
    if call_total == 0:
        return 0.0
    return put_total / call_total
