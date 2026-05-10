"""IV-favorability scoring primitive.

Per plan v1.2 §9.11 (Scoring Functions Module) and §17 M1.4a.

`iv_score()` answers "how favorable is the current implied-vol environment
for *selling* premium?" It blends three signals:

  rank_component       Where current IV sits in its 252-day range (iv_rank).
                       High rank → premium is rich relative to recent history.
  percentile_component What fraction of recent observations are below current
                       (iv_percentile). Robust complement to rank: insensitive
                       to outliers but sensitive to distribution density.
  iv_hv_premium        Ratio of implied (atm_iv_30d) to realized (hv_30) vol.
                       The directional edge for premium sellers — IV > HV
                       means the market is paying a risk premium that decays
                       toward HV as expiration approaches. A ratio of 1.0
                       (IV = HV) maps to 0.5 (neutral). 1.5+ → 1.0; 0.7- → 0.0.

Weights (sum to 1.0):

    score = 0.40 · rank + 0.30 · percentile + 0.30 · premium

The weights are deliberate: rank is the primary "are we in the high-IV
band" signal; percentile adds a second perspective on the same series;
the IV/HV premium is an independent dimension and is weighted equally
to percentile because IV-rank-vs-history and IV-vs-realized capture
different aspects of edge.

Edge cases:

  - `hv_30 == 0.0` (constant prices)  → premium component is the neutral
                                        0.5 prior. Cannot form an IV/HV
                                        ratio when realized vol is zero.
                                        (See plan v1.2 §9.1 hv.py docstring:
                                        "treat 0.0 HV as 'no realized motion'
                                        and ignore the IV − HV signal.")
  - Out-of-range iv_rank or iv_percentile → ValueError. These come from
                                            `engine.market_state.iv` which
                                            already guarantees [0, 1] —
                                            anything outside is a programmer
                                            error upstream and should fail
                                            loudly.
  - Negative hv_30 / atm_iv_30d → ValueError. Volatility is non-negative.

Pure function (per ADR-0005).
"""

from __future__ import annotations

from dataclasses import dataclass

from engine._utils import clip01

# Weights — must sum to 1.0 so the composite stays bounded by [0, 1].
_W_RANK = 0.40
_W_PERCENTILE = 0.30
_W_PREMIUM = 0.30

# IV/HV ratio anchors for the premium component.
# ratio at or below `_PREMIUM_RATIO_FLOOR` → premium component = 0.0
# ratio at or above `_PREMIUM_RATIO_CEIL`  → premium component = 1.0
# linear in between. ratio = 1.0 (parity) lands at 0.375 — this is by
# design: the engine treats parity as "neutral leaning slightly cheap"
# because the realized-vol estimator is backward-looking and IV is
# forward-looking; sustained IV = HV means the market expects realized
# to continue, with no extra premium for risk.
_PREMIUM_RATIO_FLOOR = 0.7
_PREMIUM_RATIO_CEIL = 1.5


@dataclass(frozen=True)
class IvScoreResult:
    """Result of `iv_score()`. Carries the score plus per-component breakdown.

    `breakdown` keys map 1:1 to the formula components — the Confidence
    Composer (§22.13) surfaces these for explainability.
    """

    score: float
    breakdown: dict[str, float]


def iv_score(
    *,
    iv_rank: float,
    iv_percentile: float,
    hv_30: float,
    atm_iv_30d: float,
) -> IvScoreResult:
    """Composite IV-favorability score in [0, 1].

    Higher values indicate a more favorable environment for selling
    premium — the market is paying for vol that historical realized
    behavior does not justify, and IV is sitting in the upper range
    of recent history.

    Args:
        iv_rank: Range-based IV rank, in [0, 1]. From
                 `engine.market_state.iv.iv_rank()`.
        iv_percentile: Count-based IV percentile, in [0, 1]. From
                       `engine.market_state.iv.iv_percentile()`.
        hv_30: 30-day annualized historical volatility (decimal; 0.22 = 22%).
               Must be >= 0.
        atm_iv_30d: Current ATM 30-day implied vol (decimal; 0.30 = 30%).
                    Must be >= 0.

    Returns:
        `IvScoreResult` with `score` in [0, 1] and a `breakdown` dict
        carrying the individual component values.

    Raises:
        ValueError: `iv_rank` or `iv_percentile` outside [0, 1], or
                    `hv_30` / `atm_iv_30d` is negative.
    """
    if not 0.0 <= iv_rank <= 1.0:
        raise ValueError(f"iv_score: iv_rank must be in [0, 1]; got {iv_rank}")
    if not 0.0 <= iv_percentile <= 1.0:
        raise ValueError(
            f"iv_score: iv_percentile must be in [0, 1]; got {iv_percentile}"
        )
    if hv_30 < 0.0:
        raise ValueError(f"iv_score: hv_30 must be >= 0; got {hv_30}")
    if atm_iv_30d < 0.0:
        raise ValueError(f"iv_score: atm_iv_30d must be >= 0; got {atm_iv_30d}")

    rank_component = iv_rank
    percentile_component = iv_percentile

    if hv_30 <= 0.0:
        # Constant-prices floor: HV degenerate, no premium signal.
        # Plan §9.1 hv.py docstring is explicit about this fallback.
        premium_component = 0.5
    else:
        ratio = atm_iv_30d / hv_30
        premium_component = clip01(
            (ratio - _PREMIUM_RATIO_FLOOR) / (_PREMIUM_RATIO_CEIL - _PREMIUM_RATIO_FLOOR)
        )

    score = clip01(
        _W_RANK * rank_component
        + _W_PERCENTILE * percentile_component
        + _W_PREMIUM * premium_component
    )

    return IvScoreResult(
        score=score,
        breakdown={
            "rank": rank_component,
            "percentile": percentile_component,
            "iv_hv_premium": premium_component,
        },
    )
