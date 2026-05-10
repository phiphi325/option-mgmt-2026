"use client";

import { useEffect } from "react";

export default function TodayError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // M0.5+ wires this into Sentry; for now just log to console.
    console.error("[/today] error:", error);
  }, [error]);

  return (
    <main className="container mx-auto py-12 max-w-3xl">
      <div className="rounded-lg border border-destructive/50 bg-destructive/5 p-6">
        <h2 className="text-lg font-semibold text-destructive">
          Something went wrong loading today's decision.
        </h2>
        <p className="mt-2 text-sm text-muted-foreground">
          {error.message || "Unknown error."}
        </p>
        {error.digest && (
          <p className="mt-1 text-xs text-muted-foreground/80">
            Digest: <code>{error.digest}</code>
          </p>
        )}
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
