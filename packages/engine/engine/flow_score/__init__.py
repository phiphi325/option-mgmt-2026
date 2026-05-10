"""Flow Score Engine — option-chain flow primitives.

Per plan v1.2 §9.3 (Flow Score Engine) and §17 M1.5.

This sub-package builds the Flow Score Engine incrementally. M1.5 ships the
two prerequisite primitives that downstream engines consume; the full V1
`compute()` orchestrator (§9.3a LOCKED contract) lands in M1.5b after
M1.5a's `gamma_score`.

  M1.5 (this milestone)
    compute_oi_walls          OI-derived support / resistance levels
                              (per §9.3 step 1: 90th-percentile-OI strikes)
    compute_dealer_gamma_proxy  Signed OI-weighted distance from spot
                              (per §9.3 step 4: V1 proxy without BS gamma;
                              replaced by E1 GEX in Phase 1.5 per ADR-0008)

  M1.5a (planned)
    scoring.gamma_score       Gamma-magnitude scoring primitive
                              (lands in engine.scoring, not here)

  M1.5b (planned)
    compute                   The V1 Flow Score Engine orchestrator
                              returning the §9.3a FlowScore contract
                              (bullish/bearish/score/bias/pin_probability/
                              gamma_risk/recommended_action/explanation)

Pure functions. No I/O. No DB. No network. Inputs are simple Python
values + frozen `OptionContract` records; outputs are floats or frozen
result dataclasses.

The OI-walls computation reuses the `OiWalls` dataclass defined in
`engine.scoring.structure`. The wiring is one-way: `flow_score` is the
*producer* of `OiWalls`; `structure_score` is the *consumer*.
"""

from __future__ import annotations

from engine.flow_score.dealer_gamma import compute_dealer_gamma_proxy
from engine.flow_score.oi_walls import compute_oi_walls

__all__ = [
    "compute_dealer_gamma_proxy",
    "compute_oi_walls",
]
