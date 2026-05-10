"""Scoring primitives — pure-function scalars in [0, 1] consumed by the engine.

Per plan v1.2 §9.11 (Scoring Functions Module, added v1.1) and §17 M1.4a.

Five named scoring primitives are planned (`iv`, `structure`, `gamma`,
`event`, plus `flow` which lives under `engine.flow_score` and orchestrates
the others). M1.4a ships the three that the Market State Engine reads:

  iv_score        IV vs history + IV vs realized; "is selling premium attractive?"
  structure_score OI walls + max-pain pin + EM containment; "how much do option
                  positioning and structure constrain spot?"
  event_score     Event proximity + kind + historical magnitude;
                  "how much event-driven uncertainty is sitting in the chain?"

The remaining two (`gamma`, M1.5a; `flow`, the existing orchestrator) land
in subsequent milestones. The wiring matrix in §9.11 spells out which
engines consume which scoring fns.

Each result type carries:
    score      float in [0, 1]   the headline scalar
    breakdown  dict[str, float]  each component's contribution, surfaced
                                 by the Confidence Composer for explainability
                                 (per §22.13: confidence breakdowns name
                                 the contributing factors and their values).

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
from engine.scoring.iv import IvScoreResult, iv_score
from engine.scoring.structure import OiWalls, StructureScoreResult, structure_score

__all__ = [
    # Tables / enums
    "EVENT_KIND_WEIGHTS",
    "EventKind",
    # Inputs
    "EventStats",
    "OiWalls",
    # Result types
    "EventScoreResult",
    "IvScoreResult",
    "StructureScoreResult",
    # Scoring fns
    "event_score",
    "iv_score",
    "structure_score",
]
