/**
 * Server-only API helper for the yearline evidence panel (OM-Y3).
 *
 * `getYearlineContext` calls `GET /engine/yearline-context` and returns the
 * panel payload (scalar context + trend series; either may be `null` →
 * the panel renders its empty/unavailable states). Read-only — no decision is
 * run; the Today screen's `DailyDecision` is unaffected.
 *
 * Server-only by construction (reads the JWT from `next/headers` cookies), like
 * `getDailyPlan`. Client components receive the payload as a prop.
 */

import { cookies } from "next/headers";

import { ApiError, api } from "../api";
import type { YearlinePanelResponse } from "../yearline-types";

const JWT_COOKIE_NAME = "access_token";

interface GetYearlineContextArgs {
  /** Underlying symbol (MSFT-only in V1). */
  ticker?: string;
}

export async function getYearlineContext(
  args: GetYearlineContextArgs = {},
): Promise<YearlinePanelResponse> {
  const cookieStore = await cookies();
  const token = cookieStore.get(JWT_COOKIE_NAME)?.value;
  if (!token) {
    throw new ApiError(
      401,
      "Not authenticated",
      "Sign in to view the yearline context.",
    );
  }

  const ticker = args.ticker ?? "MSFT";
  return api<YearlinePanelResponse>(
    `/engine/yearline-context?ticker=${encodeURIComponent(ticker)}`,
    {
      method: "GET",
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    },
  );
}
