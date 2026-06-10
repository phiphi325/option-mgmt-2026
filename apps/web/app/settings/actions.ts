"use server";

/**
 * Server actions for the Settings screen (M1.22).
 *
 * `saveProfile` is the client→server boundary the `UserStrategyProfileForm`
 * calls on Save. It runs on the server, so it can read the httpOnly
 * `access_token` cookie (via `updateProfile` → `next/headers`) that client JS
 * cannot see. This is why the mutation is a server action rather than a direct
 * `fetch` from the client component.
 *
 * It returns a `SaveProfileResult` union instead of throwing: errors thrown out
 * of a server action are masked in production, so a structured result is the
 * only reliable way to show the user a real message (a 422 validation detail,
 * a 401 session-expiry, etc.).
 */

import { ApiError } from "@/lib/api";
import { type SaveProfileResult, updateProfile } from "@/lib/api/profile";
import type { UserStrategyProfile } from "@/lib/decision-types";

export async function saveProfile(
  profile: UserStrategyProfile,
): Promise<SaveProfileResult> {
  try {
    const saved = await updateProfile(profile);
    return { ok: true, profile: saved };
  } catch (err) {
    if (err instanceof ApiError) {
      // Prefer the RFC 7807 `detail`, falling back to the `title`.
      return { ok: false, error: err.detail ?? err.title };
    }
    return {
      ok: false,
      error: "Something went wrong saving your profile. Please try again.",
    };
  }
}
