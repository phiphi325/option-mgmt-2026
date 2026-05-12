"use client";

import { useEffect } from "react";

/**
 * Today screen error boundary (M1.18).
 *
 * Inspects the error message for M1.17.5 hydration-prerequisite tags and
 * renders an actionable CTA. The error.message format is
 * "[<status>] <title>: <detail>" produced by `apps/web/lib/api.ts::ApiError`.
 *
 * Per master plan §15 (Security / Disclaimer) + §22.12 (IV history
 * validation): when prerequisites are missing, the user almost certainly
 * needs to upload a CSV — directing them is the right UX.
 */

interface ErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

interface PrereqCta {
  tag: string;
  title: string;
  description: string;
  ctaLabel: string;
}

const PREREQ_CTAS: readonly PrereqCta[] = [
  {
    tag: "missing_chain",
    title: "We need an option chain to evaluate MSFT.",
    description:
      "Upload chain.csv to populate the chain table. Once a snapshot is on file, the engine can recommend a strategy.",
    ctaLabel: "Upload chain CSV",
  },
  {
    tag: "missing_positions",
    title: "We don't see any MSFT positions on your account.",
    description:
      "Upload positions.csv (and option_positions.csv if you hold options) so the engine knows what to evaluate against.",
    ctaLabel: "Upload positions CSV",
  },
  {
    tag: "insufficient_iv_history",
    title: "Not enough IV history for a reliable decision.",
    description:
      "We need at least 30 daily iv_history rows for MSFT before the engine's IV-rank and percentile math is reliable. Upload iv_history.csv.",
    ctaLabel: "Upload IV history CSV",
  },
] as const;

function findPrereq(message: string): PrereqCta | null {
  for (const cta of PREREQ_CTAS) {
    if (message.includes(cta.tag)) return cta;
  }
  return null;
}

export default function TodayError({ error, reset }: ErrorProps) {
  useEffect(() => {
    // M0.5+ will wire this into Sentry; M1.18 keeps it console-only.
    console.error("[/today] error:", error);
  }, [error]);

  const prereq = findPrereq(error.message);

  // Hydration-prerequisite path: actionable CTA, friendly framing.
  if (prereq) {
    return (
      <main className="container mx-auto py-12 max-w-2xl px-4">
        <div
          className="rounded-lg border border-amber-300 bg-amber-50 p-6"
          data-testid="prereq-error"
          data-prereq-tag={prereq.tag}
        >
          <h2 className="text-lg font-semibold text-amber-900">{prereq.title}</h2>
          <p className="mt-2 text-sm text-amber-900/80">{prereq.description}</p>
          <p className="mt-4 text-sm text-amber-900/70">
            <strong>{prereq.ctaLabel}</strong> via the data-import endpoints
            (the upload UI lands in M1.22).
          </p>
          <button
            onClick={reset}
            className="mt-4 rounded-md border border-amber-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-amber-100"
          >
            Try again
          </button>
        </div>
      </main>
    );
  }

  // 401 path
  if (error.message.startsWith("[401")) {
    return (
      <main className="container mx-auto py-12 max-w-2xl px-4">
        <div
          className="rounded-lg border bg-card p-6"
          data-testid="auth-error"
        >
          <h2 className="text-lg font-semibold">Sign-in required</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Sign in to view today&apos;s decision. Your session may have
            expired.
          </p>
        </div>
      </main>
    );
  }

  // Generic fallback
  return (
    <main className="container mx-auto py-12 max-w-2xl px-4">
      <div
        className="rounded-lg border border-destructive/50 bg-destructive/5 p-6"
        data-testid="generic-error"
      >
        <h2 className="text-lg font-semibold text-destructive">
          Something went wrong loading today&apos;s decision.
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
