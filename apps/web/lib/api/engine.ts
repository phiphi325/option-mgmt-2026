/**
 * Server-only API helpers for the engine endpoints (M1.18).
 *
 * `getDailyPlan` is the headline call the Today screen makes. Per master plan
 * §7 + M1.17.5, the request body can be as small as `{ ticker, as_of }` — the
 * API service hydrates the rest from DB.
 *
 * Marked **server-only** because it reads the JWT from `next/headers` cookies.
 * Client components must not import from this file; they receive the
 * `DailyDecision` as a prop from a server-component page.
 *
 * RFC 7807 errors from the backend are re-thrown as `ApiError` (defined in
 * `apps/web/lib/api.ts`). The Today screen's `error.tsx` boundary then
 * renders an actionable message — for hydration-prerequisite 422s (`
 * missing_chain`, `insufficient_iv_history`, `missing_positions`), the
 * boundary surfaces a CTA pointing at the relevant CSV upload page.
 */

// NOTE: this module is **server-only** by construction — `cookies()` from
// `next/headers` is itself server-only and Next.js will throw a build error
// if it's imported from a client component. We rely on that enforcement
// instead of pulling in the `server-only` npm package (no new runtime dep).
import { cookies } from "next/headers";

import { ApiError, api } from "../api";
import type { DailyDecisionResponse } from "../decision-types";

const JWT_COOKIE_NAME = "access_token";

interface GetDailyPlanArgs {
  /** Underlying symbol (MSFT-only in V1). */
  ticker?: string;
  /**
   * Decision-time timestamp. Optional — when omitted, the API service
   * defaults to `now(UTC)`. For deterministic replay (e.g. testing /
   * cached pages), the caller should pin this to a fixed value.
   */
  asOf?: string;
}

/**
 * Fetch a `DailyDecision` via `POST /engine/daily-plan` using the M1.17.5
 * optional-inputs path — the API service hydrates from DB. Reads the JWT
 * from a `next/headers` cookie.
 *
 * Throws `ApiError` on non-2xx responses. The page's `error.tsx` boundary
 * inspects `error.status` + `error.detail` to render a friendly CTA.
 */
export async function getDailyPlan(
  args: GetDailyPlanArgs = {},
): Promise<DailyDecisionResponse> {
  const cookieStore = await cookies();
  const token = cookieStore.get(JWT_COOKIE_NAME)?.value;
  if (!token) {
    throw new ApiError(
      401,
      "Not authenticated",
      "Sign in to view today's decision.",
    );
  }

  const body: Record<string, unknown> = {
    ticker: args.ticker ?? "MSFT",
    persist: true,
  };
  if (args.asOf) {
    body.as_of = args.asOf;
  }

  return api<DailyDecisionResponse>("/engine/daily-plan", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
    // Server-component fetches are cached by default; daily-plan is
    // per-user + per-as_of, so opt out of caching.
    cache: "no-store",
  });
}
