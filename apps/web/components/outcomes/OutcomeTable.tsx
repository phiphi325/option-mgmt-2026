"use client";

/**
 * The outcome history list (M1.23). Renders one `OutcomeRow` per outcome, or an
 * empty-state hint. Newest-first ordering is the server's
 * (`evaluated_at DESC, id DESC`); this component preserves the order it's given.
 */

import { OutcomeRow } from "@/components/outcomes/OutcomeRow";
import type { Outcome } from "@/lib/outcome-types";

interface Props {
  outcomes: readonly Outcome[];
  onUpdated: (outcome: Outcome) => void;
}

export function OutcomeTable({ outcomes, onUpdated }: Props) {
  if (outcomes.length === 0) {
    return (
      <p
        data-testid="outcomes-empty"
        className="rounded-md border border-dashed border-border p-6 text-center text-sm text-muted-foreground"
      >
        No outcomes yet. Record one above to start tracking how your decisions
        play out.
      </p>
    );
  }

  return (
    <div className="space-y-3" data-testid="outcome-table">
      {outcomes.map((o) => (
        <OutcomeRow key={o.id} outcome={o} onUpdated={onUpdated} />
      ))}
    </div>
  );
}
