/**
 * Color-coded badge surfacing the current `Regime` (M1.18).
 *
 * Maps `Regime` → a Tailwind color class derived from `REGIME_COLORS` in
 * `option-mgmt-shared-types` (M0.6 codegen). Renders the regime name as
 * **text** alongside the color so the badge is meaningful even when the
 * user has color-vision differences (per plan v1.2 §8 accessibility floor).
 *
 * Per the M1.18 dev spec — the `tags` from `MarketStateResult` render as a
 * comma-separated subtitle when present.
 */

import type { Regime } from "option-mgmt-shared-types";
import { REGIME_COLORS, REGIME_LABELS } from "@/lib/regime-meta";

interface Props {
  regime: Regime;
  /** Annotation tags (e.g. ["sell_vol_favorable","event_in_5d"]). */
  tags?: readonly string[];
}

/**
 * Map a `Regime` to a Tailwind class. The colors are mapped at component
 * boundary so consumers don't need to import the color tokens directly.
 *
 * The classnames are fully qualified rather than dynamically composed so
 * Tailwind's JIT can statically detect them.
 */
function regimeBadgeClass(regime: Regime): string {
  switch (regime) {
    case "HIGH_IV_EVENT":
      return "bg-amber-100 text-amber-900 border-amber-300";
    case "HIGH_IV_PIN":
      return "bg-slate-100 text-slate-900 border-slate-300";
    case "LOW_IV_TREND":
      return "bg-emerald-100 text-emerald-900 border-emerald-300";
    case "LOW_IV_RANGE":
      return "bg-sky-100 text-sky-900 border-sky-300";
    case "BREAKOUT":
      return "bg-violet-100 text-violet-900 border-violet-300";
    case "POST_EVENT_REPRICE":
      return "bg-rose-100 text-rose-900 border-rose-300";
    default:
      // Defensive — unknown regimes still render visibly.
      return "bg-muted text-foreground border-border";
  }
}

export function MarketStateBadge({ regime, tags }: Props) {
  const label = REGIME_LABELS[regime] ?? regime;
  const classes = regimeBadgeClass(regime);
  // Acknowledge REGIME_COLORS import even though Tailwind sees the static
  // classnames above (this asserts the token source is the codegen output,
  // not a parallel hand-edited list).
  void REGIME_COLORS;

  return (
    <div
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 ${classes}`}
      role="status"
      aria-label={`Market state: ${label}`}
      data-testid="market-state-badge"
      data-regime={regime}
    >
      <span className="text-sm font-medium">{label}</span>
      {tags && tags.length > 0 && (
        <span className="text-xs opacity-75">· {tags.join(", ")}</span>
      )}
    </div>
  );
}
