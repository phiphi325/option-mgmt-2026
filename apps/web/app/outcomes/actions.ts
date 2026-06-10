"use server";

/**
 * Server actions for the Outcomes screen (M1.23).
 *
 * These are the client→server boundary the `OutcomeTracker` calls for create /
 * edit / load-more. They run on the server, so they can read the httpOnly
 * `access_token` cookie (via `lib/api/outcomes.ts` → `next/headers`) that client
 * JS cannot see — the same rationale as the M1.22 `saveProfile` action.
 *
 * Each returns a discriminated result union rather than throwing, because
 * errors thrown out of a server action are masked in production builds; a
 * structured `{ ok, error }` is the only reliable way to surface a 404/409/422
 * detail to the form.
 */

import { ApiError } from "@/lib/api";
import {
  type LoadMoreOutcomesResult,
  type OutcomeMutationResult,
  createOutcome,
  getOutcomes,
  patchOutcome,
} from "@/lib/api/outcomes";
import type { OutcomeCreateInput, OutcomePatchInput } from "@/lib/outcome-types";

/** Extract a user-facing message from an error (prefer RFC 7807 `detail`). */
function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    return err.detail ?? err.title;
  }
  return "Something went wrong. Please try again.";
}

export async function createOutcomeAction(
  input: OutcomeCreateInput,
): Promise<OutcomeMutationResult> {
  try {
    return { ok: true, outcome: await createOutcome(input) };
  } catch (err) {
    return { ok: false, error: errorMessage(err) };
  }
}

export async function patchOutcomeAction(
  id: string,
  patch: OutcomePatchInput,
): Promise<OutcomeMutationResult> {
  try {
    return { ok: true, outcome: await patchOutcome(id, patch) };
  } catch (err) {
    return { ok: false, error: errorMessage(err) };
  }
}

export async function loadMoreOutcomesAction(
  cursor: string,
): Promise<LoadMoreOutcomesResult> {
  try {
    const { outcomes, next_cursor } = await getOutcomes({ cursor });
    return { ok: true, outcomes, nextCursor: next_cursor };
  } catch (err) {
    return { ok: false, error: errorMessage(err) };
  }
}
