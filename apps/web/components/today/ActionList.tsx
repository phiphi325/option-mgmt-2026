/**
 * Recommended-actions section of the Today screen (M1.19).
 *
 * Replaces the M1.18 `<PlaceholderCard milestone="M1.19">`. Coordinates the
 * parallel arrays on `DailyDecision` — `recommendation.actions[]`,
 * `executions[]`, `collar_structures[]` (all index-aligned per M1.11b/M1.13) —
 * and renders one `ActionRow` per action. Handles the NO_OP / empty state with
 * a "Hold" message.
 *
 * Presentational (no `"use client"`).
 */

import { ActionRow } from "./ActionRow";
import type { DailyDecision } from "@/lib/decision-types";

interface Props {
  decision: DailyDecision;
}

export function ActionList({ decision }: Props) {
  const actions = decision.recommendation?.actions ?? [];
  const executions = decision.executions ?? [];
  const collarStructures = decision.collar_structures ?? [];

  if (actions.length === 0 || actions[0]?.emit === "NO_OP") {
    return (
      <div
        className="rounded-lg border border-border bg-muted/30 p-4 text-sm text-muted-foreground"
        data-testid="action-list-no-op"
      >
        <p className="font-medium text-foreground">Hold — no action recommended today</p>
        <p className="mt-1 text-xs">
          Market conditions do not favour entering a position.
        </p>
      </div>
    );
  }

  return (
    <section aria-label="Recommended actions" data-testid="action-list">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        Actions
      </h2>
      <ol className="space-y-2">
        {actions.map((action, i) => (
          <ActionRow
            key={i}
            index={i}
            action={action}
            execution={executions[i] ?? null}
            collarStructure={collarStructures[i] ?? null}
          />
        ))}
      </ol>
    </section>
  );
}
