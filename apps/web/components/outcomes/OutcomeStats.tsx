"use client";

/**
 * At-a-glance outcome summary (M1.23): counts by decision quality + an
 * error-type histogram. Computed over the **currently-loaded** rows only (the
 * `/outcomes` API is cursor-paginated; an all-time aggregate is a Phase-2/3
 * endpoint — see the M1.23 dev spec). Pure function of props.
 */

import type {
  Outcome,
  OutcomeError,
  OutcomeQuality,
} from "@/lib/outcome-types";

type QualityKey = OutcomeQuality | "unrated";

const QUALITY_ORDER: readonly QualityKey[] = ["good", "neutral", "bad", "unrated"];

interface Props {
  outcomes: readonly Outcome[];
}

export function OutcomeStats({ outcomes }: Props) {
  const quality: Record<QualityKey, number> = {
    good: 0,
    neutral: 0,
    bad: 0,
    unrated: 0,
  };
  const errors = new Map<OutcomeError, number>();

  for (const o of outcomes) {
    const key: QualityKey = o.decision_quality ?? "unrated";
    quality[key] += 1;
    errors.set(o.error_type, (errors.get(o.error_type) ?? 0) + 1);
  }

  const errorEntries = [...errors.entries()].sort((a, b) => b[1] - a[1]);

  return (
    <section
      className="rounded-lg border bg-card p-6 shadow-sm"
      data-testid="outcome-stats"
    >
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Summary
        </h2>
        <span className="text-xs text-muted-foreground" data-testid="stats-total">
          over {outcomes.length} loaded
        </span>
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {QUALITY_ORDER.map((k) => (
          <div key={k} className="rounded-md border border-border p-3">
            <dt className="text-xs capitalize text-muted-foreground">{k}</dt>
            <dd
              className="text-lg font-semibold tabular-nums"
              data-testid={`stats-quality-${k}`}
            >
              {quality[k]}
            </dd>
          </div>
        ))}
      </dl>

      {errorEntries.length > 0 && (
        <div className="mt-4">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">
            Error types
          </p>
          <ul className="mt-2 flex flex-wrap gap-2">
            {errorEntries.map(([type, count]) => (
              <li
                key={type}
                data-testid={`stats-error-${type}`}
                className="rounded-full border border-border px-3 py-1 text-xs"
              >
                {type.replace(/_/g, " ")}{" "}
                <span className="font-semibold tabular-nums">{count}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
