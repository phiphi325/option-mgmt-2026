"""Expected-slippage scoring for the Execution Feasibility Module.

Per plan v1.2 §9.8.

The plan calls `expected_slippage(q, qty)` without spelling out the
formula. V1 prior: half-spread + size impact.

Two components:

  - **Half-spread**: the minimum cost to cross the spread. A patient
    limit-order at mid still won't fill instantly; an aggressive
    marketable-limit pays the half-spread immediately.
  - **Size impact**: scales with `qty / OI` — a small order vs. deep OI
    has negligible impact; an order approaching the displayed OI
    walks the book and adds extra slippage on top of the half-spread.

V1 formula:

    half_spread = max(ask − bid, 0) / 2
    size_impact = (ask − bid) × clip01(qty / max(oi, 1))
    expected_slippage = half_spread + size_impact

Returned in **dollars per contract** (so a $0.10 slippage on a 100-share
contract is $10 of real-world cost). The Master Decision Engine (M1.13)
will multiply by quantity for the total estimated-cost line on
`DailyDecision`.

Phase 4 ML may learn `size_impact` from realized fill data; the
half-spread term is mathematically unavoidable for marketable orders.
"""

from __future__ import annotations

from engine._utils import clip01

# Size-impact multiplier — the fraction of the spread the order walks
# when `qty == OI`. V1 prior is 1.0 (a full-OI order walks one entire
# spread further). Phase 4 ML may learn this; for V1 we err on the
# pessimistic side so the composer's `illiquidity_penalty` doesn't
# under-bake the cost of large orders.
_SIZE_IMPACT_MULTIPLIER: float = 1.0


def expected_slippage(
    *,
    bid: float | None,
    ask: float | None,
    oi: int,
    qty: int,
) -> float:
    """Estimated slippage from mid in dollars-per-contract.

    Args:
        bid:  Quote bid (per share). `None` → treated as broken quote
              and returns 0.0 (the caller should already be filtering
              via `liquidity_score`, which catches the same case).
        ask:  Quote ask (per share). Same `None` semantics.
        oi:   Open interest at the strike. Floored at 1 to avoid
              division by zero on the size-impact term.
        qty:  Number of contracts the user intends to trade. Negative
              quantities are coerced to absolute value (the slippage
              cost is the same whether you're buying or selling).

    Returns `≥ 0` dollars per contract.
    """
    if bid is None or ask is None or ask <= bid:
        return 0.0

    spread = ask - bid
    half_spread = spread / 2.0

    effective_oi = max(oi, 1)  # floor to avoid div-by-zero
    qty_abs = abs(qty)
    impact_fraction = clip01(qty_abs / float(effective_oi))
    size_impact = spread * _SIZE_IMPACT_MULTIPLIER * impact_fraction

    return half_spread + size_impact
