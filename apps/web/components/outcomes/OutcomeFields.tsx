"use client";

/**
 * Shared controlled fields for an outcome (M1.23). Used by both the
 * `OutcomeEntryForm` (create) and the `OutcomeRow` editor (patch) so the field
 * set + control types never diverge. Purely presentational — owns no state; the
 * parent holds `OutcomeFormValues` and receives patches via `onChange`.
 *
 * Dependency-free (Path A): native `<select>` / `<input>` / `<textarea>`, no
 * shadcn. The three nullable / tri-state fields use a `""` sentinel option that
 * `lib/outcome-form.ts` maps to `null`.
 *
 * `idPrefix` namespaces the field testids (`field-${idPrefix}-${name}`) so the
 * create form (`new`) and each row editor (the outcome id) stay distinct.
 */

import type { Regime } from "option-mgmt-shared-types";

import type { OutcomeFormValues } from "@/lib/outcome-form";
import {
  OUTCOME_ERROR_OPTIONS,
  OUTCOME_QUALITY_OPTIONS,
  REGIME_OPTIONS,
  type OutcomeError,
  type OutcomeQuality,
} from "@/lib/outcome-types";

interface Props {
  idPrefix: string;
  values: OutcomeFormValues;
  onChange: (patch: Partial<OutcomeFormValues>) => void;
  disabled?: boolean;
}

const SELECT_CLASS =
  "block w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50";
const INPUT_CLASS = SELECT_CLASS;

function humanize(value: string): string {
  return value.replace(/_/g, " ");
}

export function OutcomeFields({ idPrefix, values, onChange, disabled }: Props) {
  const tid = (name: string) => `field-${idPrefix}-${name}`;

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {/* Horizon days */}
      <label className="block space-y-1.5">
        <span className="text-sm font-medium">Horizon (days)</span>
        <input
          type="number"
          min={1}
          step={1}
          data-testid={tid("horizon_days")}
          value={values.horizon_days}
          disabled={disabled}
          onChange={(e) => onChange({ horizon_days: e.target.value })}
          className={INPUT_CLASS}
        />
      </label>

      {/* Decision quality */}
      <label className="block space-y-1.5">
        <span className="text-sm font-medium">Decision quality</span>
        <select
          data-testid={tid("decision_quality")}
          value={values.decision_quality}
          disabled={disabled}
          onChange={(e) =>
            onChange({ decision_quality: e.target.value as "" | OutcomeQuality })
          }
          className={SELECT_CLASS}
        >
          <option value="">— unrated —</option>
          {OUTCOME_QUALITY_OPTIONS.map((q) => (
            <option key={q} value={q}>
              {q}
            </option>
          ))}
        </select>
      </label>

      {/* Error type */}
      <label className="block space-y-1.5">
        <span className="text-sm font-medium">Error type</span>
        <select
          data-testid={tid("error_type")}
          value={values.error_type}
          disabled={disabled}
          onChange={(e) => onChange({ error_type: e.target.value as OutcomeError })}
          className={SELECT_CLASS}
        >
          {OUTCOME_ERROR_OPTIONS.map((x) => (
            <option key={x} value={x}>
              {humanize(x)}
            </option>
          ))}
        </select>
      </label>

      {/* Actual regime realized */}
      <label className="block space-y-1.5">
        <span className="text-sm font-medium">Actual regime</span>
        <select
          data-testid={tid("actual_regime_realized")}
          value={values.actual_regime_realized}
          disabled={disabled}
          onChange={(e) =>
            onChange({ actual_regime_realized: e.target.value as "" | Regime })
          }
          className={SELECT_CLASS}
        >
          <option value="">— unknown —</option>
          {REGIME_OPTIONS.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
      </label>

      {/* Regime match (tri-state) */}
      <label className="block space-y-1.5">
        <span className="text-sm font-medium">Regime match</span>
        <select
          data-testid={tid("regime_match")}
          value={values.regime_match}
          disabled={disabled}
          onChange={(e) =>
            onChange({ regime_match: e.target.value as "" | "true" | "false" })
          }
          className={SELECT_CLASS}
        >
          <option value="">— unknown —</option>
          <option value="true">Yes</option>
          <option value="false">No</option>
        </select>
      </label>

      {/* Realized P&L */}
      <label className="block space-y-1.5">
        <span className="text-sm font-medium">Realized PnL (USD)</span>
        <input
          type="text"
          inputMode="decimal"
          placeholder="e.g. 1250.00"
          data-testid={tid("pnl_realized")}
          value={values.pnl_realized}
          disabled={disabled}
          onChange={(e) => onChange({ pnl_realized: e.target.value })}
          className={INPUT_CLASS}
        />
      </label>

      {/* Unrealized P&L */}
      <label className="block space-y-1.5">
        <span className="text-sm font-medium">Unrealized PnL (USD)</span>
        <input
          type="text"
          inputMode="decimal"
          placeholder="e.g. -300.00"
          data-testid={tid("pnl_unrealized")}
          value={values.pnl_unrealized}
          disabled={disabled}
          onChange={(e) => onChange({ pnl_unrealized: e.target.value })}
          className={INPUT_CLASS}
        />
      </label>

      {/* Notes */}
      <label className="block space-y-1.5 sm:col-span-2">
        <span className="text-sm font-medium">Notes</span>
        <textarea
          rows={2}
          placeholder="Optional — what happened, what you'd do differently."
          data-testid={tid("notes")}
          value={values.notes}
          disabled={disabled}
          onChange={(e) => onChange({ notes: e.target.value })}
          className={INPUT_CLASS}
        />
      </label>
    </div>
  );
}
