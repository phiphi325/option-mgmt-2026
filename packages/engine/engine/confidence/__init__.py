"""Confidence Composer (M1.10) — multiplicative-penalty composer.

Per plan v1.2 §9.7 (Confidence Composer) and §22.13 (multiplicative
redesign — the canonical V1 formula). ADR-0003 is the architectural
anchor.

Public surface:

    types:
        ConfidenceInputs, ConfidenceBreakdown,
        Weights, PositiveWeights, PenaltyCaps
    composer:
        compose(inputs, weights) -> (confidence, breakdown)
    components:
        compute_flow_alignment, compute_structure_alignment,
        compute_regime_match, compute_signal_alignment,
        compute_event_risk_penalty, compute_illiquidity_penalty,
        compute_confidence_inputs
    yaml loader:
        load_weights_yaml(path), load_default_weights()
    in-code defaults:
        DEFAULT_WEIGHTS — canonical V1 weights (mirrors weights.yaml)

`DEFAULT_WEIGHTS` exists so the engine has a no-I/O default suitable
for use inside pure functions (per ADR-0005). The on-disk
`packages/engine/config/weights.yaml` is the source-of-truth for
deployable hot-swap (ADR-0008 Phase 1.5). A unit test asserts the two
representations stay in sync.

Bumping the values? Update both `DEFAULT_WEIGHTS` and `weights.yaml`
(and bump `version` in both). The drift test will fail until they
agree.
"""

from __future__ import annotations

from typing import Final

from engine.confidence.components import (
    compute_confidence_inputs,
    compute_event_risk_penalty,
    compute_flow_alignment,
    compute_illiquidity_penalty,
    compute_regime_match,
    compute_signal_alignment,
    compute_structure_alignment,
)
from engine.confidence.compose import compose
from engine.confidence.types import (
    ConfidenceBreakdown,
    ConfidenceInputs,
    PenaltyCaps,
    PositiveWeights,
    Weights,
)
from engine.confidence.yaml_loader import load_default_weights, load_weights_yaml

# In-code default — kept in sync with packages/engine/config/weights.yaml
# (a unit test enforces equality).
DEFAULT_WEIGHTS: Final[Weights] = Weights(
    version="v2.0",
    positive_weights=PositiveWeights(
        flow=0.30,
        struct=0.25,
        regime=0.25,
        signal=0.20,
    ),
    penalty_caps=PenaltyCaps(
        event=0.30,
        liquidity=0.25,
    ),
)


__all__ = [
    "DEFAULT_WEIGHTS",
    "ConfidenceBreakdown",
    "ConfidenceInputs",
    "PenaltyCaps",
    "PositiveWeights",
    "Weights",
    "compose",
    "compute_confidence_inputs",
    "compute_event_risk_penalty",
    "compute_flow_alignment",
    "compute_illiquidity_penalty",
    "compute_regime_match",
    "compute_signal_alignment",
    "compute_structure_alignment",
    "load_default_weights",
    "load_weights_yaml",
]
