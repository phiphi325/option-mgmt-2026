"""Flow Score Engine — V1 LOCKED `compute()` orchestrator + primitives.

Per plan v1.2 §9.3 (Flow Score Engine), §9.3a (V1 LOCKED contract),
§22.2 (FlowScore schema reconciliation), and §17 M1.5 + M1.5b.

Built incrementally across milestones:

  M1.5 (shipped)
    compute_oi_walls           OI-derived support/resistance (§9.3 step 1)
    compute_dealer_gamma_proxy  Signed OI · (K-S) sum (§9.3 step 4, V1 proxy)

  M1.5b (this milestone)
    compute                    V1 LOCKED Flow Score orchestrator (§9.3a)
    FlowScore / Bias /         V1 LOCKED contract types (§22.2)
        RecommendedAction
    skew_25d                   V1 stub (returns 0; needs M1.6 Greeks)
    futures_basis              V1 stub (returns 0; needs Phase 2 data)
    sigmoid_pin                Multiplicative pin-probability estimator
    render_explanation         Human-readable rationale builder

The orchestrator composes the four scoring primitives (iv / structure /
event / gamma from `engine.scoring`), the OI / dealer-gamma primitives
from this package, and the max-pain / PCR primitives from
`engine.market_state`, into a single `FlowScore` result.

Pure functions per ADR-0005 — no I/O, no DB, no clock, no env.
"""

from __future__ import annotations

from engine.flow_score.compute import compute
from engine.flow_score.dealer_gamma import compute_dealer_gamma_proxy
from engine.flow_score.explanation import render_explanation
from engine.flow_score.futures_basis import futures_basis
from engine.flow_score.oi_walls import compute_oi_walls
from engine.flow_score.pin_probability import sigmoid_pin
from engine.flow_score.skew import skew_25d
from engine.flow_score.types import Bias, FlowScore, RecommendedAction

__all__ = [
    # M1.5b — V1 LOCKED orchestrator + types
    "Bias",
    "FlowScore",
    "RecommendedAction",
    "compute",
    # M1.5b — supporting primitives
    "futures_basis",
    "render_explanation",
    "sigmoid_pin",
    "skew_25d",
    # M1.5 — primitives
    "compute_dealer_gamma_proxy",
    "compute_oi_walls",
]
