"use client";

import { useEffect } from "react";

/**
 * Outcomes screen error boundary (M1.23).
 *
 * The `getOutcomes` server fetch throws `ApiError` on non-2xx; its `.message`
 * is `"[<status>] <title>: <detail>"` (per `apps/web/lib/api.ts`). The expected
 * failure for the list GET is a 401 (no/expired session), so we special-case it
 * with a sign-in prompt and otherwise show a generic message. Mirrors
 * `app/settings/error.tsx`.
 */

interface ErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function OutcomesError({ error, reset }: ErrorProps) {
  useEffect(() => {
    console.error("[/outcomes] error:", error);
  }, [error]);

  if (error.message.startsWith("[401")) {
    return (
      <main className="container mx-auto py-12 max-w-2xl px-4">
        <div className="rounded-lg border bg-card p-6" data-testid="auth-error">
          <h2 className="text-lg font-semibold">Sign-in required</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Sign in to view or record outcomes. Your session may have expired.
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
          Something went wrong loading your outcomes.
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
