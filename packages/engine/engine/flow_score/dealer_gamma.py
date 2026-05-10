"""Dealer-gamma proxy.

Per plan v1.2 §9.3 step 4 and §17 M1.5.

The **dealer-gamma proxy** approximates the sign and magnitude of the
options-dealer community's net gamma exposure around spot. It is a V1
proxy — the plan §9.3 formula uses BS gamma per contract, which the
engine cannot compute until M1.6 ships Black–Scholes. M1.5 ships a
constant-gamma proxy (gamma ≡ 1 per contract); Phase 1.5's E1 GEX
module replaces this with the proper signed-gamma computation per
[ADR-0008](../../docs/decisions/0008-enhancement-adoption-roadmap.md).

## Formula

For each contract `c` whose `expiry` is in `expiry_focus`:

  sign = -1 if c is a call (dealer assumed long calls in hedge book)
       = +1 if c is a put  (dealer assumed short puts)
  contribution = sign · OI(c) · (strike(c) - spot)

  proxy = Σ contribution over c in focus

The §9.3 sign convention says **"negative = short gamma above spot
(volatility amplifier)."** Verify against the formula:

  - Call above spot (K > S): sign=-1, (K-S)>0 → contribution < 0. ✔
  - Call below spot (K < S): sign=-1, (K-S)<0 → contribution > 0.
  - Put  above spot (K > S): sign=+1, (K-S)>0 → contribution > 0.
  - Put  below spot (K < S): sign=+1, (K-S)<0 → contribution < 0.

So:
  - Negative result → dealers net short gamma (vol *amplifier* — they
    must chase spot to delta-hedge).
  - Positive result → dealers net long gamma (vol *dampener* — they
    mean-revert spot through their delta hedge).

The magnitude is unbounded and **not unit-meaningful** without the
gamma curve. Downstream consumers (Flow Score Engine's `compute()` in
M1.5b, and the E1 GEX module in Phase 1.5) normalize it before use.

## Why this proxy?

The plan §9.3 formula is `Σ γ · OI · (K - S)`. Without BS γ available
at M1.5, three options exist:

1. **Constant γ ≡ 1** (this implementation). Cheap, no Greeks dependency.
   Loses the ATM gamma peak — far-OTM strikes contribute as much as ATM.
2. **Gaussian decay weight** `exp(-0.5 · ((K-S)/σ·√τ)²)`. Mimics gamma's
   ATM peak without computing γ exactly. Needs ATM IV + DTE per expiry.
3. **Defer to M1.6** when BS γ lands. Postpones the dealer-gamma signal,
   leaves the Market State Engine without flow input until M1.6.

Option (1) is the plan-compatible V1: the §9.3 description explicitly
calls this a *proxy*, and the E1 GEX module is already scheduled to
replace it in Phase 1.5. Adding Gaussian-decay weighting (option 2)
would prejudge what the GEX module should do.

Pure function (per ADR-0005). No I/O.

Edge cases:

  - `spot <= 0` → `ValueError`.
  - Empty `expiry_focus` → `ValueError`.
  - No contracts at any focus expiry → `ValueError`. The proxy is
    undefined without a chain to scan.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from engine.types import OptionContract, OptionType

# Sign convention. Calls coefficient -1 (dealer assumed long calls in hedge
# book); puts +1 (dealer assumed short puts). Per the §9.3 directional
# interpretation: negative result = net short gamma above spot.
_CALL_SIGN = -1
_PUT_SIGN = +1


def compute_dealer_gamma_proxy(
    *,
    contracts: Sequence[OptionContract],
    spot: float,
    expiry_focus: Sequence[date],
) -> float:
    """Signed OI-weighted distance-from-spot, V1 dealer-gamma proxy.

    Args:
        contracts: Sequence of option-chain rows. Typically
                   `chain_snapshot.contracts`. Contracts outside
                   `expiry_focus` are filtered out internally; callers
                   may pass the full chain.
        spot: Current underlying spot. Must be > 0.
        expiry_focus: Iterable of `date` values naming the expiries to
                      consider. Only contracts whose `expiry` is in this
                      set contribute. Must be non-empty.

    Returns:
        Signed float. Negative = net short gamma above spot (vol
        amplifier); positive = net long gamma (vol dampener).
        Magnitude depends on chain size + OI scale and is not directly
        comparable across tickers without normalization.

    Raises:
        ValueError: `spot` <= 0, `expiry_focus` empty, or no contracts
                    at any focus expiry.
    """
    if spot <= 0.0:
        raise ValueError(
            f"compute_dealer_gamma_proxy: spot must be > 0; got {spot}"
        )

    focus = set(expiry_focus)
    if not focus:
        raise ValueError(
            "compute_dealer_gamma_proxy: expiry_focus must contain at "
            "least one expiry"
        )

    relevant = [c for c in contracts if c.expiry in focus]
    if not relevant:
        raise ValueError(
            f"compute_dealer_gamma_proxy: no contracts present for the "
            f"requested expiry_focus ({sorted(focus)})"
        )

    total = 0.0
    for c in relevant:
        sign = _CALL_SIGN if c.option_type is OptionType.CALL else _PUT_SIGN
        total += sign * c.open_interest * (c.strike - spot)
    return total
