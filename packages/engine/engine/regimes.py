"""The six locked regimes (per ADR-0002 + plan v1.2 §9.1).

Three canonical homes for the regime taxonomy:

  1. Postgres:  CREATE TYPE regime AS ENUM (...) — apps/api/app/db/migrations/versions/0001_init.py
  2. Python:    Regime str-enum (this file)
  3. TypeScript: packages/shared-types/src/regimes.ts (generated from this file)

The string values MUST match the Postgres enum literals exactly. Adding a new
regime requires (a) Alembic migration, (b) update here, (c) regen TS, (d) UI
color, (e) at least 4 new fixtures. The coupling is intentional — see ADR-0002.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class Regime(StrEnum):
    """The six canonical market-state regimes for MSFT options decisions."""

    HIGH_IV_EVENT = "HIGH_IV_EVENT"
    HIGH_IV_PIN = "HIGH_IV_PIN"
    LOW_IV_TREND = "LOW_IV_TREND"
    LOW_IV_RANGE = "LOW_IV_RANGE"
    BREAKOUT = "BREAKOUT"
    POST_EVENT_REPRICE = "POST_EVENT_REPRICE"


# Semantic UI colors — one per regime, per plan v1.2 §8 + ADR-0002.
# These are the palette tokens. Concrete hex/HSL values live in
# apps/web/app/globals.css and apps/web/tailwind.config.ts. Components
# NEVER reference raw hex — always tokens via Tailwind classes.
REGIME_COLORS: Final[dict[Regime, str]] = {
    Regime.HIGH_IV_EVENT: "amber",
    Regime.HIGH_IV_PIN: "slate",
    Regime.LOW_IV_TREND: "emerald",
    Regime.LOW_IV_RANGE: "sky",
    Regime.BREAKOUT: "violet",
    Regime.POST_EVENT_REPRICE: "rose",
}
