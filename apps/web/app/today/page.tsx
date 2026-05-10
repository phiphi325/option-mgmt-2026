import Link from "next/link";

/**
 * Today screen — the primary surface per plan v1.2 §8.
 *
 * M0.4 (this milestone): placeholder. The DailyDecisionCard, ActionList,
 * ExecutionBadge, ConfidenceBreakdownChart, ExecutionFeasibilityPanel,
 * WatchLevels, and Drawer (rationale/risks/invalidation) components land in
 * Phase 1 (M1.18 onward). Until then this page documents the upcoming shape.
 */
export default function TodayPage() {
  return (
    <main className="container mx-auto py-12 max-w-3xl">
      <header className="mb-8">
        <p className="text-sm uppercase tracking-wide text-muted-foreground">
          Today
        </p>
        <h1 className="mt-1 text-4xl font-semibold tracking-tight">
          MSFT Decision
        </h1>
        <p className="mt-3 text-sm text-muted-foreground">
          Phase 0 placeholder. Engine-driven{" "}
          <code className="text-xs rounded bg-muted px-1 py-0.5">DailyDecision</code>{" "}
          card lands in Phase 1 (M1.18 onward).
        </p>
      </header>

      <section className="rounded-lg border bg-card p-6 shadow-sm">
        <h2 className="text-lg font-medium">Awaiting engine</h2>
        <p className="mt-2 text-sm text-muted-foreground leading-relaxed">
          The Today screen will render exactly one{" "}
          <code className="text-xs rounded bg-muted px-1 py-0.5">DailyDecision</code>{" "}
          per the canonical schema in plan v1.2 §7. Once the Master Decision
          Engine ships in Phase 1, this surface will show: regime badge,
          recommended strategy, ranked actions with execution-feasibility
          annotations, formally composed confidence breakdown, watch levels,
          rationale, risks, and invalidation criteria.
        </p>
        <p className="mt-4 text-xs text-muted-foreground">
          Build progress:{" "}
          <Link
            href="https://github.com/csupenn/option-mgmt-2026"
            target="_blank"
            rel="noopener noreferrer"
            className="underline hover:text-foreground"
          >
            csupenn/option-mgmt-2026
          </Link>
        </p>
      </section>
    </main>
  );
}
