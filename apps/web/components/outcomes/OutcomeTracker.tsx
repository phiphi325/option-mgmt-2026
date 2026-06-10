"use client";

/**
 * Client orchestrator for the Outcomes screen (M1.23). Owns the list + cursor
 * state seeded from the server component's SSR fetch, and wires:
 *   - create  → prepend the new row (`OutcomeEntryForm`)
 *   - edit    → replace the row in place (`OutcomeRow` → `OutcomeTable`)
 *   - load more → append the next cursor page (`loadMoreOutcomes` action)
 *
 * No client-side data fetching on mount — the first page is SSR'd by the page
 * server component, so there is no loading flash and no `useEffect`.
 */

import { useState } from "react";

import { loadMoreOutcomesAction } from "@/app/outcomes/actions";
import { Button } from "@/components/ui/button";
import { OutcomeEntryForm } from "@/components/outcomes/OutcomeEntryForm";
import { OutcomeStats } from "@/components/outcomes/OutcomeStats";
import { OutcomeTable } from "@/components/outcomes/OutcomeTable";
import type { Outcome } from "@/lib/outcome-types";

interface Props {
  initialOutcomes: readonly Outcome[];
  initialCursor: string | null;
}

export function OutcomeTracker({ initialOutcomes, initialCursor }: Props) {
  const [outcomes, setOutcomes] = useState<Outcome[]>(() => [...initialOutcomes]);
  const [cursor, setCursor] = useState<string | null>(initialCursor);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  function handleCreated(created: Outcome) {
    setOutcomes((prev) => [created, ...prev]);
  }

  function handleUpdated(updated: Outcome) {
    setOutcomes((prev) =>
      prev.map((o) => (o.id === updated.id ? updated : o)),
    );
  }

  async function loadMore() {
    if (cursor === null || loading) return;
    setLoading(true);
    setLoadError(null);
    const result = await loadMoreOutcomesAction(cursor);
    if (result.ok) {
      setOutcomes((prev) => [...prev, ...result.outcomes]);
      setCursor(result.nextCursor);
    } else {
      setLoadError(result.error);
    }
    setLoading(false);
  }

  return (
    <div className="space-y-8" data-testid="outcome-tracker">
      <OutcomeEntryForm onCreated={handleCreated} />

      <OutcomeStats outcomes={outcomes} />

      <section className="space-y-3">
        <h2 className="text-sm font-semibold">
          History{" "}
          <span className="font-normal text-muted-foreground">
            ({outcomes.length} loaded)
          </span>
        </h2>

        <OutcomeTable outcomes={outcomes} onUpdated={handleUpdated} />

        {loadError && (
          <p className="text-sm text-destructive" data-testid="load-error">
            {loadError}
          </p>
        )}

        {cursor !== null && (
          <div className="flex justify-center">
            <Button
              type="button"
              variant="outline"
              data-testid="load-more-button"
              onClick={loadMore}
              disabled={loading}
            >
              {loading ? "Loading…" : "Load more"}
            </Button>
          </div>
        )}
      </section>
    </div>
  );
}
