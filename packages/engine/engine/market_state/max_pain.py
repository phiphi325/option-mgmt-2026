"""Max-pain primitive (CBOE-style).

Per plan v1.2 §9.1 (Market State Engine inputs) and §22.9 (canonical formula).

Max pain is the strike at which the **total dollar pain to option writers**
at expiration is minimized — i.e. the strike that "punishes" writers least
if the underlying pins there. Common pin candidate around large-OI expiries.

The formula sums per-strike pain across all open call and put OI:

  call_pain(K) = Σ over CALL contracts c:  c.open_interest * max(K − c.strike, 0)
  put_pain(K)  = Σ over PUT  contracts c:  c.open_interest * max(c.strike − K, 0)
  total(K)     = (call_pain(K) + put_pain(K)) * 100      # contract multiplier

`compute_max_pain` returns `argmin_K total(K)` over the strike set present
in the supplied contracts for the given expiry.

Pure function (per ADR-0005). No I/O. Operates on a sequence of
`OptionContract` records — no ChainSnapshot helper-method dependency, so
this primitive is independent of any future ChainSnapshot evolution
(per plan §22.4).

Edge cases:

  - No contracts at the requested expiry → `ValueError`. Max pain is not
    defined without an open chain.
  - Single strike → that strike (vacuously the minimum).
  - Ties between strikes → the lowest tied strike wins (deterministic
    via `sorted()` + `min(... key=...)` stability).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from engine.types import OptionContract, OptionType

# Standard equity-option contract multiplier (US convention).
# Plan v1.2 §22.9 names this explicitly. 100 shares per contract.
CONTRACT_MULTIPLIER = 100


def compute_max_pain(
    *,
    contracts: Sequence[OptionContract],
    expiry: date,
) -> float:
    """Strike that minimizes total dollar pain at expiration.

    Args:
        contracts: All option contracts to consider. Contracts not matching
                   `expiry` are filtered out internally; callers may pass
                   the full chain.
        expiry: The expiration date to evaluate. Only contracts at this
                expiry contribute to the pain calculation.

    Returns:
        The strike (float) that minimizes (call_pain + put_pain) * 100.

    Raises:
        ValueError: if no contracts match the requested expiry.
    """
    relevant = [c for c in contracts if c.expiry == expiry]
    if not relevant:
        raise ValueError(
            f"compute_max_pain: no contracts present for expiry {expiry.isoformat()}"
        )

    strikes = sorted({c.strike for c in relevant})

    def pain_at(strike: float) -> float:
        call_pain = sum(
            c.open_interest * max(strike - c.strike, 0.0)
            for c in relevant
            if c.option_type is OptionType.CALL
        )
        put_pain = sum(
            c.open_interest * max(c.strike - strike, 0.0)
            for c in relevant
            if c.option_type is OptionType.PUT
        )
        return (call_pain + put_pain) * CONTRACT_MULTIPLIER

    return min(strikes, key=pain_at)
