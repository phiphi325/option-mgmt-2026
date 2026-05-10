"""Scoring primitives — pure-function scalars in [0, 1] consumed by the engine.

Per plan v1.2 §9.11 (Scoring Functions Module, added v1.1) and §17 M1.4a / M1.5a.

Four named scoring primitives plus the existing `flow_score` orchestrator
(under `engine.flow_score`). M1.4a shipped the iv/structure/event triple
consumed by the Market State Engine; M1.5a adds `gamma_score`:

  iv_score        IV vs history + IV vs realized; "is selling premium attractive?"
  structure_score OI walls + max-pain pin + EM containment; "how much do option
                  positioning and structure constrain spot?"
  event_score     Event proximity + kind + historical magnitude;
                  "how much event-driven uncertainty is sitting in the chain?"
  gamma_score     Dealer-gamma proxy + gamma walls; "how much are dealers
                  amplifying or dampening spot moves?"

The wiring matrix in §9.11 spells out which engines consume which scoring fn.
`flow_score` (the orchestrator) lives under `engine.flow_score` and composes
the others to produce the V1 FlowScore contract (M1.5b).

Each result type carries:
    score      float in [0, 1]   the headline scalar
    breakdown  dict[str, float]  each component's contribution, surfaced
                                 by the Confidence Composer for explainability
                                 (per §22.13: confidence breakdowns name
                                 the contributing factors and their values).

`GammaScoreResult` additionally carries a `sign` field in `{-1, 0, +1}`
because gamma exposure is naturally directional (dampener vs amplifier).

Pure functions per ADR-0005 — no I/O, no DB, no clock, no env.
"""

from __future__ import annotations

from engine.scoring.event import (
    EVENT_KIND_WEIGHTS,
    EventKind,
    EventScoreResult,
    EventStats,
    event_score,
)
from engine.scoring.gamma import GammaScoreResult, GammaWall, gamma_score
from engine.scoring.iv import IvScoreResult, iv_score
from engine.scoring.structure import OiWalls, StructureScoreResult, structure_score

__all__ = [
    # Tables / enums
    "EVENT_KIND_WEIGHTS",
    "EventKind",
    # Inputs
    "EventStats",
    "GammaWall",
    "OiWalls",
    # Result types
    "EventScoreResult",
    "GammaScoreResult",
    "IvScoreResult",
    "StructureScoreResult",
    # Scoring fns
    "event_score",
    "gamma_score",
    "iv_score",
    "structure_score",
]
