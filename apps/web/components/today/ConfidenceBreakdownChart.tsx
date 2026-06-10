"use client";

/**
 * Confidence breakdown for the Today screen (M1.20).
 *
 * Renders the engine `ConfidenceBreakdown` (plan §22.13) as a labelled stacked
 * composition bar + a numeric legend, with the final confidence shown
 * prominently. The four positive components use the categorical chart palette
 * (`--chart-1..4`); the two penalties reuse `--destructive` / `--muted` and are
 * shown with a `−` prefix in the legend and a muted bar treatment.
 *
 * Per §22.13 the true arithmetic is `positive_score × penalty_multiplier =
 * confidence` (multiplicative), so the bar visualises component *magnitudes*
 * (open question #2 in the dev spec) while the caption carries the exact
 * arithmetic. Falls back to a placeholder when no breakdown is present.
 */

import { StackedConfidenceBar, type StackedSegment } from "@/components/charts/StackedConfidenceBar";
import type { ConfidenceBreakdown } from "@/lib/decision-types";

interface Props {
  confidence: number;
  breakdown: ConfidenceBreakdown | null | undefined;
}

type NumericKey = Exclude<keyof ConfidenceBreakdown, "weights_version">;

const SEGMENT_CONFIG: ReadonlyArray<{
  key: NumericKey;
  label: string;
  color: string;
  isPenalty?: boolean;
}> = [
  { key: "flow_alignment", label: "Flow", color: "hsl(var(--chart-1))" },
  { key: "structure_alignment", label: "Structure", color: "hsl(var(--chart-2))" },
  { key: "regime_match", label: "Regime", color: "hsl(var(--chart-3))" },
  { key: "signal_alignment", label: "Signal", color: "hsl(var(--chart-4))" },
  { key: "event_risk_penalty", label: "Event risk", color: "hsl(var(--destructive))", isPenalty: true },
  { key: "illiquidity_penalty", label: "Liquidity", color: "hsl(var(--muted))", isPenalty: true },
];

export function ConfidenceBreakdownChart({ confidence, breakdown }: Props) {
  const confidencePct = Math.round(confidence * 100);

  if (!breakdown) {
    return (
      <section aria-label="Confidence breakdown" data-testid="confidence-chart">
        <div className="mb-2 flex items-baseline justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Confidence
          </h2>
          <span
            className="tabular-nums text-2xl font-bold leading-none"
            aria-label={`${confidencePct} percent confidence`}
          >
            {confidencePct}%
          </span>
        </div>
        <p className="text-xs text-muted-foreground" data-testid="confidence-chart-no-breakdown">
          Component breakdown unavailable for this decision.
        </p>
      </section>
    );
  }

  const segments: StackedSegment[] = SEGMENT_CONFIG.map((cfg) => ({
    label: cfg.label,
    value: breakdown[cfg.key],
    color: cfg.color,
    isPenalty: cfg.isPenalty,
  }));

  return (
    <section aria-label="Confidence breakdown" data-testid="confidence-chart">
      <div className="mb-2 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Confidence
        </h2>
        <span
          className="tabular-nums text-2xl font-bold leading-none"
          aria-label={`${confidencePct} percent confidence`}
        >
          {confidencePct}%
        </span>
      </div>

      <StackedConfidenceBar segments={segments} height={36} />

      <dl className="mt-2 grid grid-cols-3 gap-x-4 gap-y-1 text-xs">
        {SEGMENT_CONFIG.map((cfg) => (
          <div key={cfg.key} className="flex items-center gap-1.5" data-testid={`legend-${cfg.key}`}>
            <span
              className="inline-block h-2 w-2 shrink-0 rounded-sm"
              style={{ backgroundColor: cfg.color }}
              aria-hidden
            />
            <dt className="text-muted-foreground">{cfg.label}</dt>
            <dd className="ml-auto tabular-nums">
              {cfg.isPenalty ? "−" : ""}
              {Math.round(breakdown[cfg.key] * 100)}%
            </dd>
          </div>
        ))}
      </dl>

      <p className="mt-1.5 flex justify-between text-[10px] text-muted-foreground/60">
        <span className="tabular-nums" data-testid="confidence-arithmetic">
          positive {Math.round(breakdown.positive_score * 100)}% &times;{" "}
          {breakdown.penalty_multiplier.toFixed(2)} = {confidencePct}%
        </span>
        <span>weights {breakdown.weights_version}</span>
      </p>
    </section>
  );
}
