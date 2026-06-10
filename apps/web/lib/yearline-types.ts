/**
 * Web-side types for the yearline evidence panel (OM-Y3).
 *
 * `YearlineContext` (the scalar card contract) comes from the generated
 * `option-mgmt-shared-types` (OM-Y1 Pydantic→TS codegen). `YearlineTrendSeries`
 * is **presentation-only** (not an engine type, never in the replay hash), so it
 * is declared here to mirror the API's `YearlineTrendSeriesModel`.
 */

import type { YearlineContext } from "option-mgmt-shared-types";

export type { YearlineContext };

/** Presentation-only trend series — parallel arrays aligned to `dates`. */
export interface YearlineTrendSeries {
  available: boolean;
  series_version: string;
  must_not_auto_execute: true;
  warning?: string | null;
  ticker?: string | null;
  as_of?: string | null;
  schema_version?: string | null;
  model_stack_version?: string | null;
  n?: number | null;
  dates?: string[] | null;
  distance_to_ma250_pct?: (number | null)[] | null;
  drawdown_so_far_pct?: (number | null)[] | null;
  active_engine?: (string | null)[] | null;
  post_confirmation_trend_state?: (string | null)[] | null;
  trend_quality?: (number | null)[] | null;
  pullback_quality?: (number | null)[] | null;
  overextension?: (number | null)[] | null;
  deterioration?: (number | null)[] | null;
  hazard_today?: (number | null)[] | null;
  p_retry_40d?: (number | null)[] | null;
  close?: number[] | null;
  ma20?: number[] | null;
  ma50?: number[] | null;
  ma250?: number[] | null;
}

/** `GET /engine/yearline-context` response — the panel payload. */
export interface YearlinePanelResponse {
  ticker: string;
  context: YearlineContext | null;
  trend_series: YearlineTrendSeries | null;
}

/** The four trust-gate horizons (days). */
export const HORIZONS = [10, 20, 40, 60] as const;
export type Horizon = (typeof HORIZONS)[number];

/**
 * One row for the headline distance-to-MA250 line chart. `distance` is `null`
 * where the series has a gap — Recharts gaps the line (`connectNulls={false}`)
 * rather than interpolating across a regime boundary (UX §6.3).
 */
export interface TrendPoint {
  date: string;
  distance: number | null;
}

/**
 * Project a `YearlineTrendSeries` to the headline distance-to-MA250 points.
 * Pure + null-preserving (a gap stays a gap). Returns `[]` when the series is
 * unavailable or has no aligned distance array.
 */
export function toDistancePoints(series: YearlineTrendSeries | null): TrendPoint[] {
  if (!series || !series.available || !series.dates) return [];
  const distances = series.distance_to_ma250_pct ?? [];
  return series.dates.map((date, i) => ({
    date,
    distance: i < distances.length ? (distances[i] ?? null) : null,
  }));
}
