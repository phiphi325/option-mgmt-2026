/**
 * Maps `EmittedAction` codes to human-readable labels for the Today screen
 * (M1.18). The mapping is intentionally exhaustive over the V1 emit set; the
 * helper `formatStrategy` falls back to a humanized snake-case rendering for
 * unknown codes so the UI doesn't crash when the engine adds new strategies.
 *
 * Per the M1.18 dev spec (`docs/phased-design/phase-1/m1.18-today-screen-scaffolding.md`).
 */

import type { EmittedAction } from "./decision-types";

/**
 * Stable display labels for the V1 emit set.
 *
 * Adding a new entry here requires no engine version bump (this file is
 * UI-only). Drift between this set and the engine's `EmittedAction` enum is
 * acceptable in V1 — the `formatStrategy` fallback covers the gap.
 */
export const STRATEGY_LABELS: Readonly<Record<string, string>> = {
  SELL_COVERED_CALL_PARTIAL: "Sell Partial Covered Call",
  SELL_COVERED_CALL_AGGRESSIVE: "Sell Aggressive Covered Call",
  ROLL_UP_AND_OUT: "Roll Up and Out",
  WHEEL_SHORT_PUT: "Wheel — Short Put",
  BUY_LONG_DATED_PUT: "Buy Long-Dated Put",
  OPEN_COLLAR: "Open Collar",
  REDUCE_COVERAGE: "Reduce Coverage",
  MONETIZE_PUT: "Monetize Put",
  NO_OP: "No Action Today",
} as const;

/**
 * Humanize an unknown snake-case emit code as a fallback. For example:
 *  - `"SHORT_STRANGLE_SIZED"` → `"Short Strangle Sized"`
 *  - `"foo"` → `"Foo"`
 *
 * Used by `formatStrategy` when an emit code isn't in `STRATEGY_LABELS`.
 */
export function humanizeSnakeCase(code: string): string {
  return code
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((part) =>
      part.length === 0
        ? ""
        : part[0].toUpperCase() + part.slice(1).toLowerCase(),
    )
    .join(" ");
}

/**
 * Return the display label for an `EmittedAction`. Falls back to a humanized
 * snake-case rendering for codes not in `STRATEGY_LABELS`. Never throws.
 */
export function formatStrategy(code: EmittedAction | string | null | undefined): string {
  if (!code) return STRATEGY_LABELS.NO_OP;
  const known = STRATEGY_LABELS[code as keyof typeof STRATEGY_LABELS];
  if (known) return known;
  return humanizeSnakeCase(String(code));
}
