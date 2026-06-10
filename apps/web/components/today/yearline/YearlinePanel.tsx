"use client";

/**
 * Yearline evidence panel container (OM-Y3).
 *
 * Composes the current-state card (`YearlineContext`) + the headline trend line
 * (`YearlineTrendSeries`). Read-only — it never changes the `DailyDecision`.
 *
 * States:
 *  - no context AND no series  → "context unavailable" placeholder.
 *  - context present           → card (renders staleness/withheld honestly).
 *  - series present            → trend line; else the chart's own empty state.
 *
 * `"use client"` because the trend chart (Recharts) is client-only.
 */

import type { YearlinePanelResponse } from "@/lib/yearline-types";

import { YearlineCard } from "./YearlineCard";
import { YearlineTrendChart } from "./YearlineTrendChart";

interface Props {
  panel: YearlinePanelResponse;
}

export function YearlinePanel({ panel }: Props) {
  const { context, trend_series } = panel;

  if (!context && !trend_series) {
    return (
      <section
        data-testid="yearline-panel-unavailable"
        aria-label="Yearline statistical context"
        className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground"
      >
        Yearline context unavailable for {panel.ticker}.
      </section>
    );
  }

  return (
    <section data-testid="yearline-panel" className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Yearline context</h3>
        <span className="text-xs text-muted-foreground">
          MA250 repair / trend · evidence only
        </span>
      </div>
      {context && <YearlineCard context={context} />}
      <YearlineTrendChart series={trend_series} />
    </section>
  );
}
