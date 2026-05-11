"""Confidence Composer — `compose()` per plan §22.13 (multiplicative).

The V1 formula:

    positive       = clip01(
                       w.positive.flow   * c.flow_alignment +
                       w.positive.struct * c.structure_alignment +
                       w.positive.regime * c.regime_match +
                       w.positive.signal * c.signal_alignment
                     )
    penalty_mult   = (1 - w.caps.event     * c.event_risk_penalty) *
                     (1 - w.caps.liquidity * c.illiquidity_penalty)
    confidence     = clip01(positive * penalty_mult)

Why multiplicative? §22.13 walks through the v1.0/v1.1 audit finding:
the additive (signed-weight) formula has an achievable range of
`[-0.20, +0.80]`, so confidence post-clip is bounded at 0.80 — not
1.0. The multiplicative redesign restores a true `[0, 1]` codomain
(perfect components × no penalties → 1.0 exactly), at the cost of
positive components no longer being separable from penalties in the
final number. The `ConfidenceBreakdown` preserves `positive_score`
and `penalty_multiplier` as separate fields so the UI can still
render the additive part as a stacked bar with the multiplier
overlay (§22.13 final paragraph).

The function is pure (per ADR-0005). All randomness, I/O, and clock
dependencies are forbidden.
"""

from __future__ import annotations

from engine._utils import clip01
from engine.confidence.types import (
    ConfidenceBreakdown,
    ConfidenceInputs,
    Weights,
)


def compose(
    inputs: ConfidenceInputs,
    weights: Weights,
) -> tuple[float, ConfidenceBreakdown]:
    """Compute composite confidence + the explainable breakdown.

    Args:
        inputs: The six raw component values in `[0, 1]`.
        weights: The weights bundle. `positive_weights` sums to 1.0;
                 `penalty_caps` each in `[0, 1]`.

    Returns:
        `(confidence, breakdown)` where `confidence ∈ [0, 1]` and
        `breakdown` carries inputs + intermediates + weights_version.

    Pure function (per ADR-0005).
    """
    positive = clip01(
        weights.positive_weights.flow * inputs.flow_alignment
        + weights.positive_weights.struct * inputs.structure_alignment
        + weights.positive_weights.regime * inputs.regime_match
        + weights.positive_weights.signal * inputs.signal_alignment
    )
    penalty_mult = (
        (1.0 - weights.penalty_caps.event * inputs.event_risk_penalty)
        * (1.0 - weights.penalty_caps.liquidity * inputs.illiquidity_penalty)
    )
    confidence = clip01(positive * penalty_mult)

    breakdown = ConfidenceBreakdown(
        flow_alignment=inputs.flow_alignment,
        structure_alignment=inputs.structure_alignment,
        regime_match=inputs.regime_match,
        signal_alignment=inputs.signal_alignment,
        event_risk_penalty=inputs.event_risk_penalty,
        illiquidity_penalty=inputs.illiquidity_penalty,
        positive_score=positive,
        penalty_multiplier=penalty_mult,
        weights_version=weights.version,
    )
    return confidence, breakdown
