/**
 * TypeScript shapes for the V1 `DailyDecision` payload (M1.18; extended M1.19).
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
 * **M1.19 note on numeric types.** The engine uses `float` throughout (per the
 * collar/execution dataclass docstrings — "Floats (not Decimals) are used
 * throughout") and the API's `to_jsonable` passes `float`/`int` straight
 * through to JSON. So strikes, premiums, P&L, slippage, and limit bands arrive
 * as JSON **numbers**, not Decimal-as-string. Dates (`expiry`) arrive as ISO
 * strings. The interfaces below reflect the real wire shape.
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

export type OrderType = "limit" | "marketable_limit";

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

/**
 * A single recommended action. `parameters` keys depend on the emit code
 * (`strike`, `expiry`, `qty`, `delta_target`, …); the engine types them as
 * `dict[str, Any]` but in V1 they are numeric. Rendered generically by
 * `ActionRow`.
 */
export interface Action {
  readonly emit: EmittedAction;
  readonly parameters?: Readonly<Record<string, number>>;
  readonly [k: string]: unknown;
}

/**
 * A single price level to monitor (M1.21). `label` is a short descriptor like
 * "max pain", "support", "resistance", "long put strike".
 *
 * NOTE (engine gap): the V1 engine `RecommendationResult` does **not** yet emit
 * a `watch_levels` field — only `rationale` / `risks` / `invalidation` /
 * `warnings`. `WatchLevels` is therefore a forward-typed seam: the component
 * renders only once a future engine milestone populates
 * `recommendation.watch_levels`. Until then it degrades to nothing.
 */
export interface WatchLevel {
  readonly price: number;
  readonly label: string;
}

export interface WatchLevels {
  readonly above: readonly WatchLevel[];
  readonly below: readonly WatchLevel[];
  readonly iv_rank_drop_below: number | null;
}

export interface RecommendationProjection {
  readonly actions?: ReadonlyArray<Action>;
  /** Rationale bullets rendered by the M1.21 "Why" drawer. */
  readonly rationale?: readonly string[];
  /** Risk caveats rendered by the M1.21 "Risks" drawer. */
  readonly risks?: readonly string[];
  /** Invalidation conditions rendered by the M1.21 drawer. */
  readonly invalidation?: readonly string[];
  /** Independent caveat strings (low confidence, event proximity, …). */
  readonly warnings?: readonly string[];
  /** Forward-typed; not emitted by the V1 engine yet (see `WatchLevels`). */
  readonly watch_levels?: WatchLevels;
  readonly [k: string]: unknown;
}

/**
 * Per-leg execution-feasibility result (engine `engine.execution.types.ExecutionLeg`,
 * plan §7). All numeric fields are JSON numbers (engine uses `float`/`int`).
 */
export interface ExecutionLeg {
  readonly leg_id: string;
  readonly liquidity_score: number;
  readonly spread_bps: number;
  readonly fill_confidence: number;
  readonly expected_slippage: number;
  readonly suggested_order_type: OrderType;
  readonly limit_price_band: readonly [number, number];
  readonly size_warnings: readonly string[];
}

/**
 * Aggregate execution-feasibility for a multi-leg action (engine
 * `engine.execution.types.Execution`). `legs` is empty for actions that open
 * no new legs (REDUCE_COVERAGE / MONETIZE_PUT / NO_OP).
 */
export interface Execution {
  readonly aggregate_liquidity_score: number;
  readonly aggregate_fill_confidence: number;
  readonly suggested_order_type: OrderType;
  readonly legs: readonly ExecutionLeg[];
  readonly notes: readonly string[];
}

/**
 * One leg of a collar (engine `engine.collar_builder.types.CollarLeg`).
 * `strike`/`delta`/`iv`/`bid`/`ask`/`mid`/`premium` are JSON numbers; `expiry`
 * is an ISO date string. Sign conventions: `delta` signed by `kind` (CALL > 0,
 * PUT < 0); `premium` signed by `side` (BUY > 0 = debit paid, SELL < 0 =
 * credit received).
 */
export interface CollarLeg {
  readonly kind: "PUT" | "CALL";
  readonly side: "BUY" | "SELL";
  readonly strike: number;
  readonly expiry: string;
  readonly qty: number;
  readonly delta: number;
  readonly iv: number;
  readonly bid: number;
  readonly ask: number;
  readonly mid: number;
  readonly premium: number;
}

/**
 * A complete collar candidate (engine `engine.collar_builder.types.CollarStructure`).
 * P&L fields are per-share numbers. `net_debit_credit > 0` = net debit paid;
 * `< 0` = net credit received.
 */
export interface CollarStructure {
  readonly name: string;
  readonly intent: "zero_cost" | "income" | "defensive";
  readonly horizon_days: number;
  readonly long_put: CollarLeg;
  readonly short_call: CollarLeg;
  readonly net_debit_credit: number;
  readonly max_gain: number;
  readonly max_loss: number;
  readonly upside_breakeven: number;
  readonly downside_breakeven: number;
  readonly capped_upside_pct: number;
  readonly protected_downside_pct: number;
  readonly confidence: number;
  readonly rationale?: readonly string[];
  readonly risks?: readonly string[];
  readonly invalidation?: readonly string[];
  readonly execution?: Execution;
  readonly [k: string]: unknown;
}

/**
 * The Confidence Composer's explainable output (engine
 * `engine.confidence.types.ConfidenceBreakdown`, plan §22.13 multiplicative
 * redesign). Four positive components + two penalties, all in `[0, 1]`, plus
 * the two §22.13 derived intermediates (`positive_score` = pre-penalty
 * weighted average; `penalty_multiplier` = aggregate multiplier). Their
 * product (post-clip) equals the final `DailyDecision.confidence`.
 */
export interface ConfidenceBreakdown {
  readonly flow_alignment: number;
  readonly structure_alignment: number;
  readonly regime_match: number;
  readonly signal_alignment: number;
  readonly event_risk_penalty: number;
  readonly illiquidity_penalty: number;
  readonly positive_score: number;
  readonly penalty_multiplier: number;
  readonly weights_version: string;
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
   * Per-action execution feasibility, parallel to
   * `recommendation.actions[]` (M1.11/M1.13). May be absent on older payloads.
   */
  readonly executions?: readonly Execution[];
  /**
   * Per-action collar structures, parallel to `recommendation.actions[]`
   * (M1.11b). `null` for non-`OPEN_COLLAR` actions; a `CollarStructure` for
   * `OPEN_COLLAR` emits. May be absent on pre-M1.11b payloads.
   */
  readonly collar_structures?: ReadonlyArray<CollarStructure | null>;
  /**
   * The Confidence Composer breakdown behind `confidence` (M1.10 / §22.13).
   * Optional only for defensiveness against partial payloads; the engine
   * always emits it.
   */
  readonly confidence_breakdown?: ConfidenceBreakdown;
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
