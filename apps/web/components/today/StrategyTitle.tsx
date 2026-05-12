/**
 * Renders the recommended strategy as a prominent headline (M1.18).
 *
 * The strategy is the action emitted by the first item in
 * `decision.recommendation.actions`. We map the emit code → human label via
 * `formatStrategy` (handles unknown codes via humanized snake-case fallback).
 *
 * Per master plan §8 (Today screen component tree) → `<StrategyTitle name=...>`.
 */

import { formatStrategy } from "@/lib/strategy-labels";

interface Props {
  /**
   * The emit code from the recommendation's first action. `null` /
   * `undefined` renders the NO_OP label, defensive against payloads
   * without a recommendation (shouldn't happen in V1).
   */
  strategy: string | null | undefined;
}

export function StrategyTitle({ strategy }: Props) {
  const label = formatStrategy(strategy);
  return (
    <div
      className="border-l-4 border-primary pl-4 py-2"
      data-testid="strategy-title"
      data-strategy={strategy ?? "NO_OP"}
    >
      <p className="text-xs uppercase tracking-wide text-muted-foreground">
        Today&apos;s strategy
      </p>
      <h2 className="mt-1 text-2xl font-semibold tracking-tight">{label}</h2>
    </div>
  );
}
