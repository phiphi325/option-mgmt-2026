"use client";

/**
 * Top-level Today-screen container (M1.18).
 *
 * Layout per master plan §8 (Today-screen component tree):
 *
 *   DecisionHeader        ← ticker / spot / as_of / freshness
 *   MarketStateBadge      ← regime + tags
 *   StrategyTitle         ← human-readable strategy name
 *   ActionList            ← M1.19 (live)
 *   ConfidenceBreakdown   ← M1.20 (live)
 *   WatchLevels + Drawers ← M1.21 (live)
 *
 * M1.18 scaffolded the first three sections + placeholder slots; M1.19–M1.21
 * filled every slot in-place. As of M1.21 the card contains no
 * `<PlaceholderCard>` elements — the Phase-1 component tree is complete.
 *
 * Marked `"use client"` because:
 *  - the regime-token color application is client-side
 *  - the page → card transition is the boundary; the page itself stays
 *    server-component for fast TTFB.
 */

import type { DailyDecision } from "@/lib/decision-types";
import { ActionList } from "./ActionList";
import { ConfidenceBreakdownChart } from "./ConfidenceBreakdownChart";
import { DecisionHeader } from "./DecisionHeader";
import { ExecutionFeasibilityPanel } from "./ExecutionFeasibilityPanel";
import { InvalidationDrawer } from "./InvalidationDrawer";
import { MarketStateBadge } from "./MarketStateBadge";
import { RationaleDrawer } from "./RationaleDrawer";
import { RisksDrawer } from "./RisksDrawer";
import { StrategyTitle } from "./StrategyTitle";
import { WatchLevels } from "./WatchLevels";

interface Props {
  decision: DailyDecision;
}

export function DailyDecisionCard({ decision }: Props) {
  // Pull strategy from the first recommendation action (V1).
  const firstAction = decision.recommendation?.actions?.[0];
  const strategy = firstAction?.emit ?? "NO_OP";

  return (
    <article
      className="grid gap-6 rounded-lg border bg-card p-6 shadow-sm max-w-4xl mx-auto"
      data-testid="daily-decision-card"
    >
      <DecisionHeader
        ticker={decision.ticker}
        spot={decision.spot}
        asOf={decision.as_of}
        dataFreshness={decision.data_freshness}
      />

      <MarketStateBadge
        regime={decision.market_state.regime}
        tags={decision.market_state.tags}
      />

      <StrategyTitle strategy={strategy} />

      {/* M1.19 — live actions + per-leg execution feasibility (replaces the
          M1.18 placeholder slot). */}
      <ActionList decision={decision} />

      {/* M1.20 — confidence breakdown + aggregate execution feasibility
          (replaces the M1.18 placeholder slot). */}
      <ConfidenceBreakdownChart
        confidence={decision.confidence}
        breakdown={decision.confidence_breakdown}
      />
      <ExecutionFeasibilityPanel executions={decision.executions ?? []} />

      {/* M1.21 — watch levels + Why/Risks/Invalidation drawers (replaces the
          final M1.18 placeholder slot; completes the Phase-1 component tree). */}
      <WatchLevels
        above={decision.recommendation?.watch_levels?.above ?? []}
        below={decision.recommendation?.watch_levels?.below ?? []}
        ivRankDropBelow={decision.recommendation?.watch_levels?.iv_rank_drop_below ?? null}
      />
      <div
        className="divide-y divide-border rounded-md border border-border"
        data-testid="rationale-section"
      >
        <RationaleDrawer
          label="Why"
          items={decision.recommendation?.rationale ?? []}
          defaultOpen
          className="px-3"
        />
        <RisksDrawer items={decision.recommendation?.risks ?? []} />
        <InvalidationDrawer items={decision.recommendation?.invalidation ?? []} />
      </div>

      <footer
        className="border-t border-border pt-4 text-xs text-muted-foreground"
        data-testid="decision-footer"
      >
        <p>
          decision_id: <code className="text-[10px]">{decision.decision_id}</code>
        </p>
        <p className="mt-0.5">
          engine v{decision.engine_version} · weights{" "}
          {decision.weights_version} ·{" "}
          <span title={decision.inputs_hash}>
            hash <code className="text-[10px]">{decision.inputs_hash.slice(0, 19)}…</code>
          </span>
        </p>
      </footer>
    </article>
  );
}
