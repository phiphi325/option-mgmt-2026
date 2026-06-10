"use client";

/**
 * Headline distance-to-MA250 trend line (OM-Y3, scope: card + headline line).
 *
 * The single §6 "Panel B" line: `distance_to_ma250_pct` over `dates`, with a
 * 0% reference line = the yearline. Gaps (`null`) are NOT interpolated
 * (`connectNulls={false}`) — a gap marks a regime where the metric doesn't
 * apply (UX §6.3). The remaining §6 panels (price/MA, trend scores, gated risk)
 * are a planned follow-up.
 */

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { type YearlineTrendSeries, toDistancePoints } from "@/lib/yearline-types";

interface Props {
  series: YearlineTrendSeries | null;
}

function formatDateTick(value: string): string {
  // "2026-05-29" → "May '26"-ish short label; keep it dependency-free.
  const [y, m] = value.split("-");
  const months = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  ];
  const mi = Number(m) - 1;
  return mi >= 0 && mi < 12 ? `${months[mi]} '${y.slice(2)}` : value;
}

export function YearlineTrendChart({ series }: Props) {
  const points = toDistancePoints(series);

  if (points.length === 0) {
    return (
      <div
        data-testid="yearline-trend-empty"
        className="rounded-md border border-dashed border-border bg-muted/30 p-6 text-center text-sm text-muted-foreground"
      >
        No trend history available.
      </div>
    );
  }

  return (
    <div data-testid="yearline-trend-chart" className="h-[220px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
          <XAxis
            dataKey="date"
            tickFormatter={formatDateTick}
            minTickGap={48}
            tick={{ fontSize: 11 }}
          />
          <YAxis
            tickFormatter={(v: number) => `${v}%`}
            width={48}
            tick={{ fontSize: 11 }}
          />
          <Tooltip
            formatter={(value) =>
              typeof value === "number"
                ? [`${value.toFixed(2)}%`, "Distance to MA250"]
                : [String(value ?? "—"), "Distance to MA250"]
            }
          />
          {/* 0% = the yearline (MA250). */}
          <ReferenceLine
            y={0}
            stroke="currentColor"
            strokeDasharray="4 4"
            label={{ value: "MA250 (yearline)", position: "insideTopRight", fontSize: 10 }}
          />
          <Line
            type="monotone"
            dataKey="distance"
            stroke="#0ea5e9"
            strokeWidth={2}
            dot={false}
            connectNulls={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
