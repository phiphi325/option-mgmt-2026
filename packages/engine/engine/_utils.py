"""Engine-internal utilities. Private to the engine package.

Per ADR-0005 the engine is pure-function. Helpers that simplify scoring
math live here. Plan v1.2 §22.5 / §22.13 reference `clip01` directly; we
register it here as the canonical engine-wide implementation.

Name-mangled module (`_utils.py`) signals "internal — not part of the
public engine API". External consumers re-implement or copy these
trivial helpers if needed; they don't import from `engine._utils`.
"""

from __future__ import annotations

import math


def clip01(x: float) -> float:
    """Clip a float to the closed unit interval [0.0, 1.0].

    Saturates rather than raising — used by scoring functions whose
    composite formulas can transiently exceed [0,1] before the final
    clip. The Confidence Composer (§22.13) and the M1.4 scoring functions
    (§22.5) both rely on this convention.
    """
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def sigmoid(x: float) -> float:
    """Standard logistic sigmoid: σ(x) = 1 / (1 + exp(-x)).

    Used by the M1.4 Market State Engine `classify()` to soften threshold-
    based regime predicates (per plan v1.2 §9.2). Numerically stable for
    extreme inputs — Python's `math.exp` underflows to 0 for very negative
    `x` (sigmoid → 0) and overflows are pre-empted by branching on sign so
    we always pass a non-positive value into `exp`.
    """
    if x >= 0.0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)
