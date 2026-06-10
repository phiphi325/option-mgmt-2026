"use client";

/**
 * Top-level Today-screen container (M1.18).
 *
 * Layout per master plan §8 (Today-screen component tree):
 *
 *   DecisionHeader        ← ticker / spot / as_of / freshness
 *   MarketStateBadge      ← regime + tags
 *   StrategyTitle         ← human-readable strategy name
 *   ActionList            ← M1.19 placeholder
 *   ConfidenceBreakdown   ← M1.20 placeholder
 *   Drawer (Why/Risks/…)  ← M1.21 placeholder
 *
 * M1.18 fills the first three sections with real data and places explicit
 * `<PlaceholderCard>` blocks for the M1.19–M1.21 slots. The grid layout
 * stays stable across those milestones; subsequent PRs replace each
 * placeholder in-place without re-architecting.
 *
 * Marked `"use client"` because:
 *  - the regime-token color application is client-side
 *  - the eventual M1.19/M1.20/M1.21 placeholders become interactive (drawer
 *    expand/collapse, hover charts)
 *  - the page → card transition is the boundary; the page itself stays
 *    server-component for fast TTFB.
 */

import type { DailyDecision } from "@/lib/decision-types";
import { ActionList } from "./ActionList";
import { ConfidenceBreakdownChart } from "./ConfidenceBreakdownChart";
import { DecisionHeader } from "./DecisionHeader";
import { ExecutionFeasibilityPanel } from "./ExecutionFeasibilityPanel";
import { MarketStateBadge } from "./MarketStateBadge";
import { StrategyTitle } from "./StrategyTitle";

interface Props {
  decision: DailyDecision;
}

interface PlaceholderProps {
  milestone: string;
  label: string;
}

function PlaceholderCard({ milestone, label }: PlaceholderProps) {
  return (
    <div
      className="rounded-lg border border-dashed border-border bg-muted/40 p-4 text-sm text-muted-foreground"
      data-testid={`placeholder-${milestone}`}
    >
      <p className="font-medium text-foreground">
        {label} <span className="text-xs">— coming in {milestone}</span>
      </p>
      <p className="mt-1 text-xs">
        Slot reserved by M1.18; replaced in-place when {milestone} ships.
      </p>
    </div>
  );
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

      {/*
       * M1.21 placeholder — explicit slot so the layout doesn't shift when
       * that milestone fills it in. The grid order matches the master plan §8
       * component tree.
       */}
      <PlaceholderCard milestone="M1.21" label="Why / Risks / Invalidation" />

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
