"""Collar Builder engine module (M1.11a).

Public API:

  - `build()`               — entry point; produces ranked collar candidates.
  - `CollarIntent`          — enum of the three V1 intents.
  - `CollarLeg`             — single leg dataclass.
  - `CollarStructure`       — complete collar candidate dataclass.

Plan refs: §9.10 (Collar Builder), §7 (schemas).
"""

from __future__ import annotations

from .build import build
from .leg_factory import make_long_put, make_short_call
from .types import CollarIntent, CollarLeg, CollarStructure

__all__ = [
    "CollarIntent",
    "CollarLeg",
    "CollarStructure",
    "build",
    "make_long_put",
    "make_short_call",
]
