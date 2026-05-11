"""Strike Selector — V1 `select_strikes()` orchestrator.

Per plan v1.2 §9.5 (Strike Selector) and §17 M1.8.

Consumes:
  - `engine.recommendation.Recommendation` (strategy_class + parameters)
  - `engine.types.ChainSnapshot` (frozen option-chain projection)

Produces:
  - `StrikeSelection` (frozen dataclass) — strategy_class + tuple of
    `StrikeLeg`s + optional `skipped_reason`.

Each `StrikeLeg` carries the selected `OptionContract`, the leg `side`
(`LONG`/`SHORT`), and the match diagnostics (target/actual delta, DTE,
mid price).

Pure functions per ADR-0005 — no I/O, no DB, no clock, no env.
"""

from __future__ import annotations

from engine.strike_selector.select import (
    DTE_MAX_DAYS,
    DTE_MIN_DAYS,
    select_strikes,
)
from engine.strike_selector.types import LegSide, StrikeLeg, StrikeSelection

__all__ = [
    "DTE_MAX_DAYS",
    "DTE_MIN_DAYS",
    "LegSide",
    "StrikeLeg",
    "StrikeSelection",
    "select_strikes",
]
