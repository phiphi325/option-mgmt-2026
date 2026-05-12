/**
 * Decision header — ticker / spot / as-of / freshness badge (M1.18).
 *
 * Per master plan §8 Today-screen component tree:
 *
 *   <DecisionHeader>
 *     <TickerSpotBlock />
 *     <AsOfBadge />
 *     <DataFreshnessBadge />     -- spot/chain/iv staleness
 *   </DecisionHeader>
 *
 * M1.18 collapses those four conceptual children into one component since
 * they share data + a single horizontal layout. Future milestones can split
 * if any sub-piece becomes interactive (e.g. clicking the freshness badge
 * to drill into per-input ages).
 */

import type { DataFreshness } from "@/lib/decision-types";

interface Props {
  ticker: string;
  spot: number;
  asOf: string;
  dataFreshness: DataFreshness;
}

function formatAsOf(asOf: string): string {
  try {
    const d = new Date(asOf);
    return d.toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      timeZoneName: "short",
    });
  } catch {
    return asOf;
  }
}

function formatSpot(spot: number): string {
  return spot.toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function DecisionHeader({ ticker, spot, asOf, dataFreshness }: Props) {
  const anyStale = dataFreshness?.any_stale === true;
  const staleTags = dataFreshness?.stale_tags ?? [];

  return (
    <header
      className="flex flex-wrap items-baseline gap-x-6 gap-y-1"
      data-testid="decision-header"
    >
      <div className="flex items-baseline gap-3">
        <span className="text-3xl font-semibold tracking-tight">{ticker}</span>
        <span className="text-xl text-muted-foreground" data-testid="spot">
          {formatSpot(spot)}
        </span>
      </div>

      <span
        className="text-xs text-muted-foreground"
        data-testid="as-of"
        title={asOf}
      >
        as of {formatAsOf(asOf)}
      </span>

      {anyStale && (
        <span
          className="inline-flex items-center gap-1 rounded border border-amber-300 bg-amber-50 px-2 py-0.5 text-xs text-amber-900"
          role="status"
          aria-label="Data may be stale"
          data-testid="freshness-stale-badge"
          title={
            staleTags.length > 0
              ? `Stale: ${staleTags.join(", ")}`
              : "One or more inputs may be stale"
          }
        >
          <span aria-hidden="true">⚠</span>
          <span>data may be stale</span>
        </span>
      )}
    </header>
  );
}
