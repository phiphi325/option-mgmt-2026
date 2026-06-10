/**
 * WatchLevels — compact pill-row of key price / IV checkpoints to monitor
 * (M1.21). Above/below price alerts + an IV-rank drop threshold.
 *
 * Engine gap: the V1 `RecommendationResult` does not yet emit `watch_levels`
 * (only rationale / risks / invalidation / warnings). This component is a
 * forward-typed seam — it returns `null` until a future engine milestone
 * populates `recommendation.watch_levels`, so it adds no clutter today while
 * keeping the master-plan §8 component tree complete.
 *
 * Plain Tailwind pills (the repo has no shadcn `Badge`), matching
 * `MarketStateBadge` / `ExecutionBadge`. Presentational — no `"use client"`.
 */

import type { WatchLevel } from "@/lib/decision-types";

interface Props {
  above: readonly WatchLevel[];
  below: readonly WatchLevel[];
  ivRankDropBelow: number | null;
}

function LevelPill({ direction, level }: { direction: "up" | "down"; level: WatchLevel }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5 text-xs">
      <span aria-hidden>{direction === "up" ? "↑" : "↓"}</span>
      <span className="tabular-nums">${level.price.toFixed(0)}</span>
      <span className="text-muted-foreground">{level.label}</span>
    </span>
  );
}

export function WatchLevels({ above, below, ivRankDropBelow }: Props) {
  const hasAny = above.length > 0 || below.length > 0 || ivRankDropBelow !== null;
  if (!hasAny) return null;

  return (
    <section className="flex flex-wrap items-center gap-2" aria-label="Watch levels" data-testid="watch-levels">
      <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Monitor</span>
      {above.map((level, i) => (
        <LevelPill key={`above-${i}`} direction="up" level={level} />
      ))}
      {below.map((level, i) => (
        <LevelPill key={`below-${i}`} direction="down" level={level} />
      ))}
      {ivRankDropBelow !== null && (
        <span
          className="inline-flex items-center rounded-full border border-border bg-muted/50 px-2 py-0.5 text-xs tabular-nums"
          data-testid="watch-levels-iv"
        >
          IV rank drop &lt; {ivRankDropBelow}
        </span>
      )}
    </section>
  );
}
