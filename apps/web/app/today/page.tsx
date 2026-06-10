/**
 * Today screen — the primary surface per master plan v1.2 §8 (M1.18).
 *
 * Server component. Fetches a `DailyDecision` via `POST /engine/daily-plan`
 * using the M1.17.5 optional-inputs path (the API service hydrates from DB),
 * then hands it to the client-side `DailyDecisionCard` for rendering.
 *
 * Error path: 401 / 422 / 5xx all bubble up to `error.tsx`. The error
 * boundary inspects the `ApiError.status` + `detail` and renders an
 * actionable CTA (e.g. "upload chain.csv" when `missing_chain` fires).
 */

import { DailyDecisionCard } from "@/components/today/DailyDecisionCard";
import { YearlinePanel } from "@/components/today/yearline/YearlinePanel";
import { getDailyPlan } from "@/lib/api/engine";
import { getYearlineContext } from "@/lib/api/yearline";
import type { YearlinePanelResponse } from "@/lib/yearline-types";

export const dynamic = "force-dynamic"; // per-user + per-now; never cache

export default async function TodayPage() {
  // V1 hardcodes the ticker; M4.11 generalizes to multi-ticker.
  const ticker = "MSFT";
  const { decision } = await getDailyPlan({ ticker });

  // The yearline panel is supplementary (OM-Y3) — a failure here must NOT
  // break the headline decision. Degrade to no panel.
  let yearline: YearlinePanelResponse | null = null;
  try {
    yearline = await getYearlineContext({ ticker });
  } catch {
    yearline = null;
  }

  return (
    <main className="container mx-auto py-12 px-4 space-y-8">
      <DailyDecisionCard decision={decision} />
      {yearline && <YearlinePanel panel={yearline} />}
    </main>
  );
}
