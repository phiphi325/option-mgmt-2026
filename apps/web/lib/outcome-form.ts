/**
 * Pure form-value mapping for the Outcomes screen (M1.23).
 *
 * The DOM controls are string-based (selects, text inputs), and three fields
 * are nullable / tri-state on the wire (`decision_quality`,
 * `actual_regime_realized`, `regime_match`). This module is the single source
 * of truth for the string-form ↔ wire-shape conversions, shared by the
 * `OutcomeEntryForm` (create) and the `OutcomeRow` editor (patch) so the two
 * never diverge. Kept pure (no React) so it is unit-testable on its own.
 *
 * P&L note: `pnl_*` are sent as the raw trimmed string the user typed (or null
 * for empty) — the server's `Decimal` is authoritative, so we never parse to a
 * JS number on the write path (avoids float-rounding the stored value).
 */

import type { Regime } from "option-mgmt-shared-types";

import type {
  Outcome,
  OutcomeCreateInput,
  OutcomeError,
  OutcomePatchInput,
  OutcomeQuality,
} from "./outcome-types";

/** String-friendly mirror of the editable outcome fields (DOM control values). */
export interface OutcomeFormValues {
  horizon_days: string;
  pnl_realized: string;
  pnl_unrealized: string;
  decision_quality: "" | OutcomeQuality;
  error_type: OutcomeError;
  actual_regime_realized: "" | Regime;
  regime_match: "" | "true" | "false";
  notes: string;
}

/** Blank form for the create path (`error_type` defaults to "none"; horizon 7). */
export const EMPTY_OUTCOME_FORM: OutcomeFormValues = {
  horizon_days: "7",
  pnl_realized: "",
  pnl_unrealized: "",
  decision_quality: "",
  error_type: "none",
  actual_regime_realized: "",
  regime_match: "",
  notes: "",
};

/** Seed the editable form from an existing outcome (the row editor). */
export function outcomeToFormValues(o: Outcome): OutcomeFormValues {
  return {
    horizon_days: String(o.horizon_days),
    pnl_realized: o.pnl_realized ?? "",
    pnl_unrealized: o.pnl_unrealized ?? "",
    decision_quality: o.decision_quality ?? "",
    error_type: o.error_type,
    actual_regime_realized: o.actual_regime_realized ?? "",
    regime_match:
      o.regime_match === null ? "" : o.regime_match ? "true" : "false",
    notes: o.notes ?? "",
  };
}

function emptyToNull(s: string): string | null {
  const t = s.trim();
  return t === "" ? null : t;
}

function parseRegimeMatch(v: "" | "true" | "false"): boolean | null {
  return v === "" ? null : v === "true";
}

/** Map the form to a `POST /outcomes` body (create). */
export function formValuesToCreateInput(
  v: OutcomeFormValues,
  dailyDecisionId: string,
): OutcomeCreateInput {
  return {
    daily_decision_id: dailyDecisionId.trim(),
    horizon_days: Number(v.horizon_days),
    pnl_realized: emptyToNull(v.pnl_realized),
    pnl_unrealized: emptyToNull(v.pnl_unrealized),
    decision_quality: v.decision_quality === "" ? null : v.decision_quality,
    error_type: v.error_type,
    actual_regime_realized:
      v.actual_regime_realized === "" ? null : v.actual_regime_realized,
    regime_match: parseRegimeMatch(v.regime_match),
    notes: emptyToNull(v.notes),
  };
}

/** Map the form to a `PATCH /outcomes/{id}` body (full field set; edit). */
export function formValuesToPatchInput(v: OutcomeFormValues): OutcomePatchInput {
  return {
    horizon_days: Number(v.horizon_days),
    pnl_realized: emptyToNull(v.pnl_realized),
    pnl_unrealized: emptyToNull(v.pnl_unrealized),
    decision_quality: v.decision_quality === "" ? null : v.decision_quality,
    error_type: v.error_type,
    actual_regime_realized:
      v.actual_regime_realized === "" ? null : v.actual_regime_realized,
    regime_match: parseRegimeMatch(v.regime_match),
    notes: emptyToNull(v.notes),
  };
}

/** True when the form can be submitted as a create (decision id + valid horizon). */
export function canCreate(values: OutcomeFormValues, dailyDecisionId: string): boolean {
  const horizon = Number(values.horizon_days);
  return (
    dailyDecisionId.trim() !== "" &&
    Number.isInteger(horizon) &&
    horizon >= 1
  );
}
