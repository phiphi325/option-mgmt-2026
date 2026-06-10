"use client";

/**
 * Strategy-profile editor for the Settings screen (M1.22).
 *
 * Dependency-free (M1.22 Path A). The shipped dev spec built this on
 * react-hook-form + zod + @tanstack/react-query + shadcn `Form`/`Select`/
 * `Slider`/`Tooltip`/`toast` primitives — none of which are installed in
 * `apps/web` (the only UI deps are `@radix-ui/react-dialog` + `recharts`), and
 * the pnpm lockfile cannot be regenerated in this environment. Rather than add
 * five runtime dependencies for one form, this uses native controlled inputs
 * (`<select>`, `<input type="range">`, `<input type="checkbox">`) + React
 * `useState`, and saves via the `saveProfile` **server action**.
 *
 * Why no client-side schema library: the engine `UserStrategyProfile` is 8
 * simple fields whose only constraints are per-field ranges + enum membership.
 * Native `min`/`max`/`step` + `<option>` sets keep the inputs in range by
 * construction, and the API's `ProfileUpdateRequest` (Pydantic `extra="forbid"`
 * + `Field` validators) is the authoritative validator. A zod mirror would be
 * a second source of truth to drift, with nothing to validate that the controls
 * don't already constrain. (The spec's cross-field rules — `delta_min <
 * delta_max`, `dte_min < dte_max` — referenced fields that do not exist on the
 * real schema.)
 *
 * Save is a full replacement (`PUT /profile`). Presets fill the form without
 * saving; the user reviews and clicks Save.
 */

import { type FormEvent, useState } from "react";

import { saveProfile } from "@/app/settings/actions";
import { Button } from "@/components/ui/button";
import { PersonaPresetButtons } from "@/components/settings/PersonaPresetButtons";
import type {
  IncomeNeed,
  ProfileStyle,
  RiskTolerance,
  UserStrategyProfile,
} from "@/lib/decision-types";
import { formatPct } from "@/lib/format";

interface Props {
  initialProfile: UserStrategyProfile;
}

type SaveStatus = "idle" | "saving" | "saved" | "error";

const RISK_OPTIONS: ReadonlyArray<{ value: RiskTolerance; label: string }> = [
  { value: "conservative", label: "Conservative" },
  { value: "moderate", label: "Moderate" },
  { value: "aggressive", label: "Aggressive" },
];

const INCOME_OPTIONS: ReadonlyArray<{ value: IncomeNeed; label: string }> = [
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
];

const STYLE_OPTIONS: ReadonlyArray<{ value: ProfileStyle; label: string }> = [
  { value: "income", label: "Income" },
  { value: "balanced", label: "Balanced" },
  { value: "growth", label: "Growth" },
];

export function UserStrategyProfileForm({ initialProfile }: Props) {
  // `baseline` is the last-saved profile (drives dirty detection + Reset).
  const [baseline, setBaseline] = useState<UserStrategyProfile>(initialProfile);
  const [values, setValues] = useState<UserStrategyProfile>(initialProfile);
  const [status, setStatus] = useState<SaveStatus>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const dirty = JSON.stringify(values) !== JSON.stringify(baseline);

  /** Replace the whole working profile (presets, reset) + clear save status. */
  function applyProfile(next: UserStrategyProfile) {
    setValues(next);
    setStatus("idle");
    setErrorMsg(null);
  }

  /** Patch a single field + clear any stale save status. */
  function patch(next: Partial<UserStrategyProfile>) {
    applyProfile({ ...values, ...next });
  }

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setStatus("saving");
    setErrorMsg(null);
    const result = await saveProfile(values);
    if (result.ok) {
      // Trust the persisted echo as the new baseline (PUT is a full replace).
      setBaseline(result.profile);
      setValues(result.profile);
      setStatus("saved");
    } else {
      setErrorMsg(result.error);
      setStatus("error");
    }
  }

  return (
    <div className="space-y-8" data-testid="profile-form-root">
      <PersonaPresetButtons onSelect={applyProfile} />

      <form
        onSubmit={handleSubmit}
        data-testid="profile-form"
        className="space-y-6 rounded-lg border bg-card p-6 shadow-sm"
      >
        {/* Risk tolerance */}
        <label className="block space-y-1.5">
          <span className="text-sm font-medium">Risk tolerance</span>
          <select
            data-testid="field-risk_tolerance"
            value={values.risk_tolerance}
            onChange={(e) =>
              patch({ risk_tolerance: e.target.value as RiskTolerance })
            }
            className="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {RISK_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <span className="block text-xs text-muted-foreground">
            How much downside variance you&apos;ll absorb. Drives collar/put bias.
          </span>
        </label>

        {/* Income need */}
        <label className="block space-y-1.5">
          <span className="text-sm font-medium">Income need</span>
          <select
            data-testid="field-income_need"
            value={values.income_need}
            onChange={(e) => patch({ income_need: e.target.value as IncomeNeed })}
            className="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {INCOME_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <span className="block text-xs text-muted-foreground">
            Premium-income preference. Drives covered-call coverage at fixed risk.
          </span>
        </label>

        {/* Strategy style */}
        <label className="block space-y-1.5">
          <span className="text-sm font-medium">Strategy style</span>
          <select
            data-testid="field-style"
            value={values.style}
            onChange={(e) => patch({ style: e.target.value as ProfileStyle })}
            className="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {STYLE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <span className="block text-xs text-muted-foreground">
            Primary objective for trade selection (drives §22.8 rule predicates).
          </span>
        </label>

        {/* Max position % */}
        <label className="block space-y-1.5">
          <span className="flex items-baseline justify-between text-sm font-medium">
            <span>Max position size</span>
            <span
              data-testid="readout-max_position_pct"
              className="tabular-nums text-muted-foreground"
            >
              {formatPct(values.max_position_pct)}
            </span>
          </span>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            data-testid="field-max_position_pct"
            value={values.max_position_pct}
            onChange={(e) => patch({ max_position_pct: Number(e.target.value) })}
            className="block w-full accent-primary"
          />
          <span className="block text-xs text-muted-foreground">
            Cap on a single position as a fraction of portfolio NAV.
          </span>
        </label>

        {/* Max coverage % */}
        <label className="block space-y-1.5">
          <span className="flex items-baseline justify-between text-sm font-medium">
            <span>Max coverage</span>
            <span
              data-testid="readout-max_coverage_pct"
              className="tabular-nums text-muted-foreground"
            >
              {formatPct(values.max_coverage_pct)}
            </span>
          </span>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            data-testid="field-max_coverage_pct"
            value={values.max_coverage_pct}
            onChange={(e) => patch({ max_coverage_pct: Number(e.target.value) })}
            className="block w-full accent-primary"
          />
          <span className="block text-xs text-muted-foreground">
            Fraction of long shares that may be written against (covered calls +
            collar shorts).
          </span>
        </label>

        {/* Drawdown tolerance */}
        <label className="block space-y-1.5">
          <span className="flex items-baseline justify-between text-sm font-medium">
            <span>Drawdown tolerance</span>
            <span
              data-testid="readout-drawdown_tolerance"
              className="tabular-nums text-muted-foreground"
            >
              {formatPct(values.drawdown_tolerance)}
            </span>
          </span>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            data-testid="field-drawdown_tolerance"
            value={values.drawdown_tolerance}
            onChange={(e) =>
              patch({ drawdown_tolerance: Number(e.target.value) })
            }
            className="block w-full accent-primary"
          />
          <span className="block text-xs text-muted-foreground">
            Worst-case loss you&apos;ll tolerate before protection is required.
          </span>
        </label>

        {/* Min IV rank for short premium */}
        <label className="block space-y-1.5">
          <span className="flex items-baseline justify-between text-sm font-medium">
            <span>Min IV rank to sell premium</span>
            <span
              data-testid="readout-min_iv_rank_for_short_premium"
              className="tabular-nums text-muted-foreground"
            >
              {values.min_iv_rank_for_short_premium}
            </span>
          </span>
          <input
            type="range"
            min={0}
            max={100}
            step={1}
            data-testid="field-min_iv_rank_for_short_premium"
            value={values.min_iv_rank_for_short_premium}
            onChange={(e) =>
              patch({
                min_iv_rank_for_short_premium: Math.round(Number(e.target.value)),
              })
            }
            className="block w-full accent-primary"
          />
          <span className="block text-xs text-muted-foreground">
            Below this IV rank (0–100), the engine prefers protective puts / no
            action over selling premium.
          </span>
        </label>

        {/* Prefer collars */}
        <label className="flex items-start gap-3">
          <input
            type="checkbox"
            data-testid="field-prefer_collars_over_covered_calls"
            checked={values.prefer_collars_over_covered_calls}
            onChange={(e) =>
              patch({ prefer_collars_over_covered_calls: e.target.checked })
            }
            className="mt-0.5 h-4 w-4 rounded border-input accent-primary"
          />
          <span className="space-y-0.5">
            <span className="block text-sm font-medium">
              Prefer collars over covered calls
            </span>
            <span className="block text-xs text-muted-foreground">
              When both qualify, bias toward a collar (insurance) instead of a
              plain covered call (income).
            </span>
          </span>
        </label>

        {/* Status + actions */}
        <div className="flex items-center justify-between gap-3 pt-2">
          <p
            data-testid="save-status"
            aria-live="polite"
            className={
              status === "error"
                ? "text-sm text-destructive"
                : "text-sm text-muted-foreground"
            }
          >
            {status === "saving" && "Saving…"}
            {status === "saved" && "Saved. Your next daily plan uses these settings."}
            {status === "error" && (errorMsg ?? "Save failed.")}
            {status === "idle" && dirty && "Unsaved changes."}
          </p>
          <div className="flex shrink-0 gap-3">
            <Button
              type="button"
              variant="outline"
              data-testid="reset-button"
              disabled={!dirty || status === "saving"}
              onClick={() => applyProfile(baseline)}
            >
              Reset
            </Button>
            <Button
              type="submit"
              data-testid="save-button"
              disabled={!dirty || status === "saving"}
            >
              {status === "saving" ? "Saving…" : "Save settings"}
            </Button>
          </div>
        </div>
      </form>

      {/* Account section — Phase 1 placeholder (full flow is Phase 2). */}
      <section
        className="border-t border-border pt-6"
        data-testid="account-section"
      >
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Account
        </h2>
        <p className="text-sm text-muted-foreground">
          Password change and account deletion available in a future update.
        </p>
      </section>
    </div>
  );
}
