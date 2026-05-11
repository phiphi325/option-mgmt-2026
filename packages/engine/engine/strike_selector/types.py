"""Strike Selector result types.

Per plan v1.2 §9.5 (Strike Selector) and §17 M1.8.

The Strike Selector takes a `Recommendation` + `ChainSnapshot` and picks
concrete option-leg `OptionContract`s — using BS delta-matching against
the `Recommendation.parameters.target_delta` and DTE-matching against
`target_dte`. The output is one or more `StrikeLeg`s wrapped in a
`StrikeSelection` result.

## Leg structure per strategy class

  COVERED_CALL_AGGRESSIVE / PARTIAL  → 1 short call leg
  PROTECTIVE_PUT                     → 1 long put leg
  COLLAR                             → 1 short call + 1 long put (2 legs)
  REDUCE_CALL_COVERAGE               → 0 legs (requires existing position
                                       context, not in V1 engine scope)
  WAIT / MONITOR                     → 0 legs

When no legs are selected (either by strategy class or because no
contract clears the filters), `legs` is empty and `skipped_reason` is
non-`None` explaining why.

## Side convention

`StrikeLeg.side` ∈ `{"LONG", "SHORT"}` reflects the direction the user
WOULD TAKE on the leg, NOT the contract's option type:

  - Selling a covered call → side="SHORT" on a CALL
  - Buying a protective put → side="LONG" on a PUT
  - Collar = SHORT call + LONG put

Sign of `delta_target` is on the leg-side convention too: positive for
calls, negative for puts. `delta_actual` is the BS delta of the
selected contract (NOT signed by leg side); consumers should reconcile
side against delta-sign themselves if they need a position-aware
delta.

Frozen dataclasses per [ADR-0005](../decisions/0005-engine-pure-function-discipline.md).
The `legs` tuple is naturally immutable; the contained
`OptionContract`s are pydantic `frozen=True` and therefore immutable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from engine.recommendation.types import StrategyClass
from engine.types import OptionContract


class LegSide(StrEnum):
    """Direction of a single option leg in a multi-leg strategy.

    `LONG` = buyer (pays premium, owns optionality).
    `SHORT` = seller / writer (collects premium, takes obligation).

    Wire-stable values — these flow through to position-management
    code and to the UI.
    """

    LONG = "LONG"
    SHORT = "SHORT"


@dataclass(frozen=True)
class StrikeLeg:
    """A single option leg with the selected contract + match diagnostics.

    Fields:
        contract:        The selected `OptionContract` from the chain.
                         Carries strike, expiry, option_type, IV, OI,
                         volume, bid/ask/mid.
        side:            `LegSide.LONG` or `LegSide.SHORT`.
        delta_target:    The target delta (signed: positive for calls,
                         negative for puts).
        delta_actual:    The BS delta at the contract's strike, using
                         its own IV. Same sign convention as
                         `delta_target`.
        delta_distance:  `|delta_actual − delta_target|`. Lower is
                         a better match.
        dte_actual:      Days-to-expiry of the selected contract,
                         using the M1.6 365-day convention.
        mid_price:       The mid quote at selection. May be `None`
                         when the chain quote is incomplete; downstream
                         consumers must handle `None`.

    All numeric fields are bounded as documented. Frozen dataclass.
    """

    contract: OptionContract
    side: LegSide
    delta_target: float
    delta_actual: float
    delta_distance: float
    dte_actual: int
    mid_price: float | None


@dataclass(frozen=True)
class StrikeSelection:
    """The Strike Selector's output for one `Recommendation`.

    Fields:
        strategy_class:  Echoed from the input `Recommendation` for
                         downstream traceability.
        legs:            Zero or more `StrikeLeg`s. Order is stable:
                         for `COLLAR`, the first leg is always the
                         SHORT call, the second is the LONG put.
        skipped_reason:  Human-readable explanation when `legs` is
                         empty. `None` when at least one leg was
                         selected.

    The `legs` tuple is empty exactly when:
      - `strategy_class` is `WAIT`, `MONITOR`, or
        `REDUCE_CALL_COVERAGE`, OR
      - No contract in the chain cleared the DTE / liquidity / side
        filters for any required leg.

    Frozen dataclass per ADR-0005.
    """

    strategy_class: StrategyClass
    legs: tuple[StrikeLeg, ...] = field(default_factory=tuple)
    skipped_reason: str | None = None
