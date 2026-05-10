// Surfaces the Regime taxonomy + UI color tokens to the web app.
//
// This module is the apps/web entry point for the M0.6+ shared types — it
// re-exports the canonical Regime + REGIME_COLORS from `option-mgmt-shared-types`
// (generated from `packages/engine/engine/regimes.py` per ADR-0002).
//
// Components MUST import Regime / REGIME_COLORS from here, not redefine the
// taxonomy locally. Adding a new regime means: (a) Alembic migration,
// (b) update `packages/engine/engine/regimes.py`, (c) re-run shared-types
// codegen, (d) add a Tailwind color token + CSS variable. CI's drift check
// fails any commit that updates the Python without regenerating the TS.

import { REGIME_COLORS, Regime } from "option-mgmt-shared-types";

export type { Regime };
export { REGIME_COLORS };

/** Human-readable label for a Regime, used in UI cards and badges. */
export const REGIME_LABELS: Readonly<Record<Regime, string>> = {
  HIGH_IV_EVENT: "High IV — Event Window",
  HIGH_IV_PIN: "High IV — Pin Risk",
  LOW_IV_TREND: "Low IV — Trending",
  LOW_IV_RANGE: "Low IV — Range-Bound",
  BREAKOUT: "Breakout",
  POST_EVENT_REPRICE: "Post-Event Reprice",
} as const;
