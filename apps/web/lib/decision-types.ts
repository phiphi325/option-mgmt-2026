/**
 * TypeScript shapes for the V1 `DailyDecision` payload (M1.18).
 *
 * The API serializes `DailyDecision` as a loose `dict[str, Any]` for V1 (per
 * the M1.14 PR body — `apps/api/app/schemas/engine.py::decision_to_jsonable_dict`).
 * The codegen at `packages/shared-types/scripts/generate.py` doesn't yet cover
 * the recursive decision shape (M1.18+ tightens it when the Today screen needs
 * strict TS codegen).
 *
 * Until then, M1.18 declares **API-internal** TS interfaces covering the fields
 * the Today screen actually renders. The contract is intentionally narrow:
 *  - Required fields are the ones the M1.18 components depend on.
 *  - Other fields are `unknown` so the runtime payload's extras (which the
 *    engine adds freely) don't break the type contract.
 *
 * When the engine response schema is tightened in M1.18+, this file gets
 * deleted and the types move into the codegen output.
 */

import type { Regime } from "option-mgmt-shared-types";

export type EmittedAction =
  | "SELL_COVERED_CALL_PARTIAL"
  | "SELL_COVERED_CALL_AGGRESSIVE"
  | "ROLL_UP_AND_OUT"
  | "WHEEL_SHORT_PUT"
  | "BUY_LONG_DATED_PUT"
  | "OPEN_COLLAR"
  | "REDUCE_COVERAGE"
  | "MONETIZE_PUT"
  | "NO_OP"
  | string; // permissive — engine may add new emit codes

export interface DataFreshness {
  readonly any_stale: boolean;
  readonly spot_age_seconds?: number | null;
  readonly chain_age_seconds?: number | null;
  readonly iv_age_seconds?: number | null;
  readonly stale_tags?: readonly string[];
  readonly [k: string]: unknown;
}

export interface MarketStateProjection {
  readonly regime: Regime;
  readonly regime_score: number;
  readonly tags?: readonly string[];
  readonly [k: string]: unknown;
}

export interface FlowScoreProjection {
  readonly score: number;
  readonly bias: string;
  readonly recommended_action: string;
  readonly [k: string]: unknown;
}

export interface RecommendationProjection {
  readonly actions?: ReadonlyArray<{
    readonly emit: EmittedAction;
    readonly parameters?: Readonly<Record<string, number>>;
    readonly [k: string]: unknown;
  }>;
  readonly [k: string]: unknown;
}

/**
 * Minimal `DailyDecision` shape the Today screen depends on. Permissive
 * (`[k: string]: unknown`) so engine-added fields don't break.
 */
export interface DailyDecision {
  readonly decision_id: string;
  readonly as_of: string;
  readonly ticker: string;
  readonly spot: number;
  readonly market_state: MarketStateProjection;
  readonly flow_score: FlowScoreProjection;
  readonly recommendation: RecommendationProjection;
  readonly confidence: number;
  readonly engine_version: string;
  readonly weights_version: string;
  readonly inputs_hash: string;
  readonly data_freshness: DataFreshness;
  /**
   * V1 design choice (M1.14): the response is intentionally loose. M1.18+
   * tightens this once the Today screen's components stabilize. Until then,
   * fields not enumerated above are passed through as `unknown` to avoid
   * gating UI work on the schema-tightening milestone.
   */
  readonly [k: string]: unknown;
}

/**
 * The wrapping envelope returned by `POST /engine/daily-plan` (per
 * `apps/api/app/schemas/decision.py::DailyDecisionResponse`).
 */
export interface DailyDecisionResponse {
  readonly decision: DailyDecision;
  /**
   * `true` when this call inserted a fresh `daily_decisions` row;
   * `false` when ON CONFLICT (user_id, inputs_hash) fired (idempotent retry).
   */
  readonly is_new_row: boolean;
}
