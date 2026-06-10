/**
 * Numeric formatting helpers for the Today-screen action list (M1.19).
 *
 * The emit-code → human label mapping lives in `@/lib/strategy-labels`
 * (`formatStrategy`) and is reused as-is — this module only adds the numeric
 * formatters M1.19's `ActionRow` / `ExecutionBadge` need. All inputs are JSON
 * numbers (the engine uses `float` throughout — see `decision-types.ts`).
 *
 * Per the M1.19 dev spec (`docs/phased-design/phase-1/m1.19-action-list-execution-badge.md`),
 * with the spec's `format.ts` `emitToVerb`/`emitToLabel` dropped in favour of
 * the existing `formatStrategy`.
 */

const USD = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** Format a strike as USD, e.g. `380` → `"$380.00"`. */
export function formatStrike(strike: number): string {
  return USD.format(strike);
}

/**
 * Format a signed premium / net debit-credit with an explicit `cr`/`dr` tag.
 *
 * Sign convention (engine): a **negative** value is a credit *received*, a
 * **positive** value is a debit *paid* — for both a leg's `premium` (signed by
 * side) and a structure's `net_debit_credit`. We show the magnitude plus a tag
 * rather than a bare minus sign so the direction is unambiguous to the user,
 * e.g. `-0.02` → `"$0.02 cr"`, `1.50` → `"$1.50 dr"`.
 */
export function formatPremium(value: number): string {
  const tag = value < 0 ? "cr" : "dr";
  return `${USD.format(Math.abs(value))} ${tag}`;
}

/** Format a basis-points value, e.g. `12.4` → `"12 bps"`. */
export function formatBps(bps: number): string {
  return `${Math.round(bps)} bps`;
}

/** Format a `[0, 1]` fraction as a whole percentage, e.g. `0.87` → `"87%"`. */
export function formatPct(fraction: number): string {
  return `${Math.round(fraction * 100)}%`;
}
