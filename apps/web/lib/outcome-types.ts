/**
 * TypeScript wire shapes for the `/outcomes` API (M1.23 — Outcomes screen).
 *
 * Mirrors the shipped `apps/api/app/schemas/outcome.py` (M1.17). Kept in its
 * own module (like `yearline-types.ts`) since outcomes are a distinct domain
 * from the `DailyDecision` payload.
 *
 * **Numeric wire types (verified against the API).** Unlike the `DailyDecision`
 * payload — where the engine uses `float` and values arrive as JSON numbers —
 * the `outcomes` P&L columns are Pydantic `Decimal`, and this codebase
 * serialises `Decimal` → JSON **string** (Pydantic v2 default; confirmed by the
 * `/market` smoke test coercing `float(body["spot"])` while the `/profile` test
 * asserts a bare `== 0.25` for a `float` field). So `pnl_realized` /
 * `pnl_unrealized` are `string | null` here, and the formatter
 * (`lib/format.ts::formatPnl`) coerces with `Number(...)` for display only —
 * the raw string is what we send back to the API, so we never float-round a
 * stored value.
 *
 * `id` / `daily_decision_id` are UUID strings; `evaluated_at` is an ISO string.
 */

import type { Regime } from "option-mgmt-shared-types";

export type OutcomeQuality = "good" | "neutral" | "bad";

export type OutcomeError =
  | "early_roll"
  | "late_roll"
  | "missed_breakout"
  | "over_coverage"
  | "under_coverage"
  | "wrong_strike"
  | "ignored_event"
  | "none";

export type OutcomeSource = "manual" | "auto";

/** One outcome row (engine-agnostic; mirrors `OutcomeResponse`). */
export interface Outcome {
  readonly id: string;
  readonly daily_decision_id: string;
  readonly evaluated_at: string;
  readonly horizon_days: number;
  /** Decimal on the server → JSON string on the wire (see module docstring). */
  readonly pnl_realized: string | null;
  readonly pnl_unrealized: string | null;
  readonly decision_quality: OutcomeQuality | null;
  /** Non-null in responses — the server defaults it to `"none"`. */
  readonly error_type: OutcomeError;
  readonly actual_regime_realized: Regime | null;
  readonly regime_match: boolean | null;
  readonly notes: string | null;
  readonly source: OutcomeSource;
}

/** `GET /outcomes` envelope. `next_cursor` is opaque; pass back as `?cursor=`. */
export interface OutcomeListResponse {
  readonly outcomes: readonly Outcome[];
  readonly next_cursor: string | null;
}

/**
 * `POST /outcomes` body. `source` is server-set (`manual`), so it's omitted.
 * `pnl_*` are sent as strings (or null) — the server parses to `Decimal`.
 */
export interface OutcomeCreateInput {
  readonly daily_decision_id: string;
  readonly horizon_days: number;
  readonly pnl_realized: string | null;
  readonly pnl_unrealized: string | null;
  readonly decision_quality: OutcomeQuality | null;
  readonly error_type: OutcomeError;
  readonly actual_regime_realized: Regime | null;
  readonly regime_match: boolean | null;
  readonly notes: string | null;
}

/** `PATCH /outcomes/{id}` body — every field optional (partial update). */
export type OutcomePatchInput = Partial<Omit<OutcomeCreateInput, "daily_decision_id">>;

/** Selectable error types for the form (all but the implicit `"none"` default). */
export const OUTCOME_ERROR_OPTIONS: readonly OutcomeError[] = [
  "none",
  "early_roll",
  "late_roll",
  "missed_breakout",
  "over_coverage",
  "under_coverage",
  "wrong_strike",
  "ignored_event",
];

export const OUTCOME_QUALITY_OPTIONS: readonly OutcomeQuality[] = [
  "good",
  "neutral",
  "bad",
];

export const REGIME_OPTIONS: readonly Regime[] = [
  "HIGH_IV_EVENT",
  "HIGH_IV_PIN",
  "LOW_IV_TREND",
  "LOW_IV_RANGE",
  "BREAKOUT",
  "POST_EVENT_REPRICE",
];
