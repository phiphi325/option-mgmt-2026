/**
 * Yearline current-state card (OM-Y3) — renders from the scalar `YearlineContext`.
 *
 * Gate-respect on the display boundary (UX §4.1 + handoff §3.2):
 *  - per-horizon P(retry≤H) shown ONLY where `gate_passed[h]`; otherwise
 *    "withheld · building evidence" (the withheld state IS the signal — never hidden).
 *  - P(success) / composite shown ONLY where `success_gate_passed`.
 *  - dormant (`repair_active === false` ⇒ `p_retry == {}`): show the trend state,
 *    do NOT synthesize a retry probability.
 *  - `is_stale` → an explicit staleness badge.
 *  - `must_not_auto_execute` → the standing "evidence, not advice" disclaimer.
 */

import { HORIZONS, type YearlineContext } from "@/lib/yearline-types";

interface Props {
  context: YearlineContext;
}

function pct(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined ? "—" : `${(value * 100).toFixed(digits)}%`;
}

function signedPct(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) return "—";
  const s = value > 0 ? "+" : "";
  return `${s}${value.toFixed(digits)}%`;
}

const TREND_STATE_LABELS: Record<string, string> = {
  pullback_but_intact: "Pullback, trend intact",
  indeterminate_trend: "Indeterminate",
  trend_deterioration_watch: "Deterioration watch",
};

function GatedRetryBars({ context }: { context: YearlineContext }) {
  const pRetry = context.p_retry ?? {};
  const gates = context.gate_passed ?? {};

  if (!context.repair_active) {
    const label = context.post_confirmation_trend_state
      ? (TREND_STATE_LABELS[context.post_confirmation_trend_state] ??
        context.post_confirmation_trend_state)
      : "above the yearline";
    return (
      <p
        data-testid="yearline-retry-dormant"
        className="text-sm text-muted-foreground"
      >
        Above the yearline — retry watch dormant. Trend state: <strong>{label}</strong>.
      </p>
    );
  }

  return (
    <ul data-testid="yearline-retry-bars" className="space-y-1">
      {HORIZONS.map((h) => {
        const key = String(h);
        const gated = gates[key] === true;
        const value = pRetry[key];
        return (
          <li key={h} className="flex items-center gap-2 text-sm" data-horizon={h}>
            <span className="w-12 shrink-0 tabular-nums text-muted-foreground">
              ≤{h}d
            </span>
            {gated && typeof value === "number" ? (
              <>
                <span
                  className="inline-block h-2 rounded bg-sky-500"
                  style={{ width: `${Math.round(value * 100)}%` }}
                  aria-hidden
                />
                <span className="tabular-nums">{pct(value)}</span>
              </>
            ) : (
              <span
                className="text-xs italic text-muted-foreground"
                data-testid={`yearline-retry-withheld-${h}`}
              >
                withheld · building evidence
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

export function YearlineCard({ context }: Props) {
  const repair = context.repair_active;
  const regimeLabel = repair ? "Repair / retry watch" : "Confirmed trend";
  const regimeClass = repair
    ? "bg-amber-100 text-amber-900 border-amber-300"
    : "bg-emerald-100 text-emerald-900 border-emerald-300";

  return (
    <section
      data-testid="yearline-card"
      aria-label="Yearline statistical context"
      className="space-y-4 rounded-lg border border-border p-4"
    >
      <header className="flex flex-wrap items-center gap-2">
        <span
          data-testid="yearline-regime-chip"
          className={`inline-flex items-center rounded-full border px-3 py-1 text-sm font-medium ${regimeClass}`}
        >
          {regimeLabel}
        </span>
        {context.is_stale && (
          <span
            data-testid="yearline-stale-badge"
            className="inline-flex items-center rounded-full border border-rose-300 bg-rose-100 px-2 py-0.5 text-xs font-medium text-rose-900"
          >
            stale
          </span>
        )}
        {context.p_retry_basis && (
          <span className="inline-flex items-center rounded-full border border-border px-2 py-0.5 text-xs text-muted-foreground">
            basis: {context.p_retry_basis}
          </span>
        )}
      </header>

      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
        <div>
          <dt className="text-muted-foreground">Distance to MA250</dt>
          <dd className="tabular-nums">{signedPct(context.distance_to_ma250_pct)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Required rebound</dt>
          <dd className="tabular-nums">{signedPct(context.required_rebound_to_ma250_pct)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Days to touch (central)</dt>
          <dd className="tabular-nums">
            {context.days_to_touch_central ?? "—"}
            {context.days_to_touch_low != null && context.days_to_touch_high != null && (
              <span className="text-muted-foreground">
                {" "}
                [{context.days_to_touch_low}–{context.days_to_touch_high}]
              </span>
            )}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Sample scope</dt>
          <dd>{context.reference_scope ?? "—"}</dd>
        </div>
      </dl>

      <div>
        <h4 className="mb-1 text-sm font-medium">P(retry ≤ H)</h4>
        <GatedRetryBars context={context} />
      </div>

      {context.success_gate_passed && context.p_success != null && (
        <div data-testid="yearline-success" className="text-sm">
          <span className="text-muted-foreground">P(success │ retry): </span>
          <span className="tabular-nums">{pct(context.p_success)}</span>
        </div>
      )}

      <footer className="border-t border-border pt-2 text-xs text-muted-foreground">
        Educational evidence, not advice. This signal never auto-executes.
      </footer>
    </section>
  );
}
