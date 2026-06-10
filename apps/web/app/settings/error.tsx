"use client";

import { useEffect } from "react";

/**
 * Settings screen error boundary (M1.22).
 *
 * The `getProfile` server fetch throws `ApiError` on non-2xx; its `.message`
 * is `"[<status>] <title>: <detail>"` (per `apps/web/lib/api.ts`). The only
 * expected failure for the profile GET is a 401 (no/expired session) — the
 * endpoint returns defaults rather than 404/422 for a fresh user — so we
 * special-case 401 with a sign-in prompt and otherwise show a generic message.
 *
 * Mirrors the shape of `app/today/error.tsx` (minus the data-import CTAs, which
 * don't apply to the profile read).
 */

interface ErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function SettingsError({ error, reset }: ErrorProps) {
  useEffect(() => {
    console.error("[/settings] error:", error);
  }, [error]);

  if (error.message.startsWith("[401")) {
    return (
      <main className="container mx-auto py-12 max-w-2xl px-4">
        <div className="rounded-lg border bg-card p-6" data-testid="auth-error">
          <h2 className="text-lg font-semibold">Sign-in required</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Sign in to view or edit your strategy settings. Your session may
            have expired.
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="container mx-auto py-12 max-w-2xl px-4">
      <div
        className="rounded-lg border border-destructive/50 bg-destructive/5 p-6"
        data-testid="generic-error"
      >
        <h2 className="text-lg font-semibold text-destructive">
          Something went wrong loading your settings.
        </h2>
        <p className="mt-2 text-sm text-muted-foreground">
          {error.message || "Unknown error."}
        </p>
        <button
          onClick={reset}
          className="mt-4 rounded-md border bg-background px-3 py-1.5 text-sm font-medium hover:bg-accent"
        >
          Try again
        </button>
      </div>
    </main>
  );
}
