"use client";

/**
 * Reusable horizontal stacked-composition bar (M1.20).
 *
 * A pure display primitive — no domain knowledge, only chart plumbing. Used by
 * `ConfidenceBreakdownChart` and reusable for any future stacked-score
 * visualisation. Built on Recharts (already a dependency via the yearline
 * OM-Y3 `YearlineTrendChart`; no new charting library), mirroring that
 * component's `ResponsiveContainer` pattern.
 *
 * Segment widths are **normalised** to sum to 1 so the bar always fills its
 * track proportionally regardless of the raw segment magnitudes (the raw
 * `[0,1]` component values do not themselves sum to 1). The numeric legend in
 * `ConfidenceBreakdownChart` carries the raw values; this bar carries the
 * relative composition.
 */

import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export interface StackedSegment {
  label: string;
  /** Raw magnitude in [0, 1]. Normalised across segments for display width. */
  value: number;
  /** CSS color string, e.g. `hsl(var(--chart-1))`. */
  color: string;
  /** Penalty segments are rendered with a muted/striped treatment. */
  isPenalty?: boolean;
}

interface Props {
  segments: StackedSegment[];
  height?: number;
  className?: string;
}

export function StackedConfidenceBar({ segments, height = 40, className }: Props) {
  const total = segments.reduce((acc, s) => acc + Math.max(s.value, 0), 0);
  // One data row; each segment is a stacked bar series keyed by its label.
  // Normalise so the row sums to 1 (avoids overflow past the [0,1] domain).
  const row: Record<string, number> = { name: 0 };
  for (const s of segments) {
    row[s.label] = total > 0 ? Math.max(s.value, 0) / total : 0;
  }

  return (
    <div className={className} data-testid="stacked-confidence-bar" style={{ width: "100%", height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={[row]} layout="vertical" margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
          <XAxis type="number" domain={[0, 1]} hide />
          <YAxis type="category" dataKey="name" hide />
          <Tooltip
            cursor={false}
            formatter={(value, name) => [`${(Number(value) * 100).toFixed(1)}%`, String(name)]}
          />
          {segments.map((s) => (
            <Bar
              key={s.label}
              dataKey={s.label}
              stackId="confidence"
              fill={s.color}
              fillOpacity={s.isPenalty ? 0.55 : 1}
              isAnimationActive={false}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
