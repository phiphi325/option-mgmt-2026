/**
 * Execution-feasibility badge for a single `ExecutionLeg` (M1.19).
 *
 * Renders fill confidence + spread (bps) as a compact pill, colour-coded by
 * fill: ≥ 80% green, 60–79% amber, < 60% red (per the M1.19 dev spec
 * acceptance criteria). The fuller detail — liquidity, suggested order type,
 * limit-price band, and any size warnings — is surfaced via the native
 * `title` tooltip, matching the repo's dependency-light component style
 * (`MarketStateBadge`); the repo has no shadcn `Badge`/`Tooltip` primitive.
 */

import { cn } from "@/lib/utils";
import { formatBps, formatPct } from "@/lib/format";
import type { ExecutionLeg } from "@/lib/decision-types";

interface Props {
  leg: ExecutionLeg;
}

/** Fully-qualified Tailwind classes so JIT can statically detect them. */
function fillClasses(fillPct: number): string {
  if (fillPct >= 80) return "bg-emerald-100 text-emerald-900 border-emerald-300";
  if (fillPct >= 60) return "bg-amber-100 text-amber-900 border-amber-300";
  return "bg-rose-100 text-rose-900 border-rose-300";
}

export function ExecutionBadge({ leg }: Props) {
  const fillPct = Math.round(leg.fill_confidence * 100);
  const [low, high] = leg.limit_price_band;
  const detailLines = [
    `Liquidity: ${formatPct(leg.liquidity_score)}`,
    `Order type: ${leg.suggested_order_type}`,
    `Limit band: ${low.toFixed(2)}–${high.toFixed(2)}`,
    ...leg.size_warnings,
  ];

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs tabular-nums",
        fillClasses(fillPct),
      )}
      title={detailLines.join("\n")}
      data-testid="execution-badge"
      data-fill={fillPct}
      data-order-type={leg.suggested_order_type}
    >
      <span>{fillPct}% fill</span>
      <span className="opacity-60">·</span>
      <span>{formatBps(leg.spread_bps)}</span>
      {leg.size_warnings.length > 0 && (
        <span aria-label="size warnings present" data-testid="execution-badge-warn">
          !
        </span>
      )}
    </span>
  );
}
