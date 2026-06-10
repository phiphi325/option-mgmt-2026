/**
 * Server-only API helpers for the `/outcomes` endpoints (M1.23).
 *
 * `getOutcomes` hydrates the Outcomes page (server component, SSR for TTFB).
 * `createOutcome` / `patchOutcome` back the manual-entry + inline-edit server
 * actions (`app/outcomes/actions.ts`).
 *
 * Server-only by construction (reads the JWT from `next/headers` cookies, same
 * as `api/engine.ts` + `api/profile.ts`). The Outcomes *components* are client
 * components and must not import this file directly — they call the server
 * actions, which is the safe client→server boundary (the `access_token` cookie
 * is httpOnly).
 *
 * Errors are re-thrown as `ApiError`; the page's `error.tsx` handles the GET
 * 401, and the server actions catch + convert to a `{ ok, error }` result.
 */

import { cookies } from "next/headers";

import { ApiError, api } from "../api";
import type {
  Outcome,
  OutcomeCreateInput,
  OutcomeListResponse,
  OutcomePatchInput,
} from "../outcome-types";

const JWT_COOKIE_NAME = "access_token";

/** Result of the `createOutcome` / `patchOutcome` server actions. */
export type OutcomeMutationResult =
  | { readonly ok: true; readonly outcome: Outcome }
  | { readonly ok: false; readonly error: string };

/** Result of the `loadMoreOutcomes` server action. */
export type LoadMoreOutcomesResult =
  | {
      readonly ok: true;
      readonly outcomes: readonly Outcome[];
      readonly nextCursor: string | null;
    }
  | { readonly ok: false; readonly error: string };

async function authHeader(): Promise<Record<string, string>> {
  const cookieStore = await cookies();
  const token = cookieStore.get(JWT_COOKIE_NAME)?.value;
  if (!token) {
    throw new ApiError(
      401,
      "Not authenticated",
      "Sign in to view or record outcomes.",
    );
  }
  return { Authorization: `Bearer ${token}` };
}

interface ListOptions {
  since?: string;
  limit?: number;
  cursor?: string;
}

/** `GET /outcomes` — cursor-paginated, newest first. Throws `ApiError` on non-2xx. */
export async function getOutcomes(
  opts: ListOptions = {},
): Promise<OutcomeListResponse> {
  const params = new URLSearchParams();
  if (opts.since) params.set("since", opts.since);
  if (opts.limit !== undefined) params.set("limit", String(opts.limit));
  if (opts.cursor) params.set("cursor", opts.cursor);
  const qs = params.toString();
  return api<OutcomeListResponse>(`/outcomes${qs ? `?${qs}` : ""}`, {
    method: "GET",
    headers: await authHeader(),
    cache: "no-store",
  });
}

/** `POST /outcomes` — create a manual outcome (201). Throws `ApiError` on non-2xx. */
export async function createOutcome(input: OutcomeCreateInput): Promise<Outcome> {
  return api<Outcome>("/outcomes", {
    method: "POST",
    headers: await authHeader(),
    body: JSON.stringify(input),
    cache: "no-store",
  });
}

/** `PATCH /outcomes/{id}` — partial update. Throws `ApiError` on non-2xx. */
export async function patchOutcome(
  id: string,
  patch: OutcomePatchInput,
): Promise<Outcome> {
  return api<Outcome>(`/outcomes/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: await authHeader(),
    body: JSON.stringify(patch),
    cache: "no-store",
  });
}
