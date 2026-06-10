/**
 * Server-only API helpers for the profile endpoints (M1.22).
 *
 * `GET /profile` hydrates the Settings page (server component, SSR for TTFB).
 * `PUT /profile` saves a full replacement of the `UserStrategyProfile`.
 *
 * Marked **server-only** by construction: like `api/engine.ts`, this module
 * reads the JWT from `next/headers` cookies, and `cookies()` is itself
 * server-only — Next.js throws a build error if it's imported from a client
 * component. The Settings *form* is a client component, so it never imports
 * this file directly; instead it calls the `saveProfile` **server action**
 * (`app/settings/actions.ts`), which is the safe client→server boundary (the
 * `access_token` cookie is httpOnly and unreadable from client JS).
 *
 * RFC 7807 errors from the backend are re-thrown as `ApiError` (defined in
 * `apps/web/lib/api.ts`). For the GET path on the Settings page, the
 * `app/settings/error.tsx` boundary inspects `ApiError.status` to render a
 * friendly sign-in prompt on 401.
 */

import { cookies } from "next/headers";

import { ApiError, api } from "../api";
import type { UserStrategyProfile } from "../decision-types";

const JWT_COOKIE_NAME = "access_token";

/**
 * Discriminated result of the `saveProfile` server action. We return a result
 * union rather than throwing across the server-action boundary: thrown errors
 * are masked (`"An error occurred in the Server Components render"`) in
 * production builds, so a structured `{ ok, error }` is the only reliable way
 * to surface a useful message to the client form. Co-located here because it
 * describes the outcome of `updateProfile`.
 */
export type SaveProfileResult =
  | { readonly ok: true; readonly profile: UserStrategyProfile }
  | { readonly ok: false; readonly error: string };

/** Build the `Authorization` header from the session cookie, or 401. */
async function authHeader(): Promise<Record<string, string>> {
  const cookieStore = await cookies();
  const token = cookieStore.get(JWT_COOKIE_NAME)?.value;
  if (!token) {
    throw new ApiError(
      401,
      "Not authenticated",
      "Sign in to view or edit your strategy profile.",
    );
  }
  return { Authorization: `Bearer ${token}` };
}

/**
 * Fetch the authenticated user's `UserStrategyProfile` via `GET /profile`.
 * The endpoint always returns a profile (sensible defaults for a fresh user),
 * so a 2xx body is always a complete profile. Throws `ApiError` on non-2xx.
 */
export async function getProfile(): Promise<UserStrategyProfile> {
  return api<UserStrategyProfile>("/profile", {
    method: "GET",
    headers: await authHeader(),
    // Per-user + mutable; never cache.
    cache: "no-store",
  });
}

/**
 * Replace the authenticated user's profile via `PUT /profile` (full
 * replacement, not PATCH). The API's `ProfileUpdateRequest` enforces
 * `extra="forbid"` + range validators, so an out-of-range or misspelled field
 * surfaces as a 422 `ApiError`. Returns the persisted profile echoed by the
 * endpoint. Throws `ApiError` on non-2xx.
 */
export async function updateProfile(
  profile: UserStrategyProfile,
): Promise<UserStrategyProfile> {
  return api<UserStrategyProfile>("/profile", {
    method: "PUT",
    headers: await authHeader(),
    body: JSON.stringify(profile),
    cache: "no-store",
  });
}
