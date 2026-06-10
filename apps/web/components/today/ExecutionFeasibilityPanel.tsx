/**
 * Compact aggregate execution-feasibility panel (M1.20).
 *
 * Summarises the primary action's aggregate fill confidence + liquidity +
 * suggested order type below the confidence chart. Per-leg detail is the M1.19
 * `ExecutionBadge`'s job; this is the decision-level roll-up. Uses a plain
 * Tailwind fill pill (the repo has no shadcn `Badge` primitive — only
 * `ui/button` + `ui/dialog`), matching `MarketStateBadge` / `ExecutionBadge`.
 *
 * Phase 2: multi-action decisions (collar + roll) should aggregate or offer a
 * selector; V1 uses `executions[0]` as the primary action.
 */

import { cn } from "@/lib/utils";
import type { Execution } from "@/lib/decision-types";

interface Props {
  executions: readonly Execution[];
}

/** Fully-qualified Tailwind classes so JIT can statically detect them. */
function fillClasses(fillPct: number): string {
  if (fillPct >= 80) return "bg-emerald-100 text-emerald-900 border-emerald-300";
  if (fillPct >= 60) return "bg-amber-100 text-amber-900 border-amber-300";
  return "bg-rose-100 text-rose-900 border-rose-300";
}

export function ExecutionFeasibilityPanel({ executions }: Props) {
  if (!executions || executions.length === 0) return null;

  const agg = executions[0];
  if (!agg) return null; // robust under noUncheckedIndexedAccess

  const fillPct = Math.round(agg.aggregate_fill_confidence * 100);
  const liqPct = Math.round(agg.aggregate_liquidity_score * 100);
  const orderType = agg.suggested_order_type === "limit" ? "Limit order" : "Marketable limit";

  return (
    <section
      className="flex flex-wrap items-center gap-3 rounded-md border border-border bg-muted/30 p-3"
      aria-label="Execution feasibility"
      data-testid="execution-feasibility-panel"
    >
      <span className="text-xs font-medium text-muted-foreground">Execution</span>
      <span
        className={cn(
          "inline-flex items-center rounded-full border px-2 py-0.5 text-xs tabular-nums",
          fillClasses(fillPct),
        )}
        data-testid="execution-feasibility-fill"
        data-fill={fillPct}
      >
        {fillPct}% fill
      </span>
      <span className="text-xs text-muted-foreground">Liquidity {liqPct}%</span>
      <span className="text-xs text-muted-foreground" aria-hidden>
        ·
      </span>
      <span className="text-xs text-muted-foreground">{orderType}</span>
      {agg.notes.map((note, i) => (
        <span key={i} className="text-xs text-amber-600" data-testid="execution-feasibility-note">
          {note}
        </span>
      ))}
    </section>
  );
}
