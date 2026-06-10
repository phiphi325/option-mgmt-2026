import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { DailyDecisionCard } from "../DailyDecisionCard";
import type { DailyDecision } from "@/lib/decision-types";

function fixture(overrides: Partial<DailyDecision> = {}): DailyDecision {
  return {
    decision_id: "dd_a1b2c3d4e5f6_1748530200",
    as_of: "2026-05-20T14:30:00Z",
    ticker: "MSFT",
    spot: 415.0,
    market_state: { regime: "HIGH_IV_PIN", regime_score: 0.78, tags: [] },
    flow_score: { score: 35, bias: "NEUTRAL_BULLISH", recommended_action: "SELL_CALL_PARTIAL" },
    recommendation: {
      actions: [
        {
          emit: "SELL_COVERED_CALL_PARTIAL",
          parameters: { target_delta: 0.25, target_dte: 30, size_pct: 0.5 },
        },
      ],
      rationale: ["IV rank 78 favours selling premium", "Pin risk elevated near max pain"],
      risks: ["Capped upside on a breakout"],
      invalidation: ["IV rank falls below 40"],
    },
    confidence: 0.62,
    confidence_breakdown: {
      flow_alignment: 0.8,
      structure_alignment: 0.7,
      regime_match: 0.9,
      signal_alignment: 0.75,
      event_risk_penalty: 0.1,
      illiquidity_penalty: 0.05,
      positive_score: 0.79,
      penalty_multiplier: 0.96,
      weights_version: "v2.0",
    },
    executions: [
      {
        aggregate_liquidity_score: 0.82,
        aggregate_fill_confidence: 0.85,
        suggested_order_type: "limit",
        legs: [],
        notes: [],
      },
    ],
    engine_version: "1.4.0",
    weights_version: "v2.0",
    inputs_hash: "sha256:abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
    data_freshness: { any_stale: false },
    ...overrides,
  };
}

describe("DailyDecisionCard", () => {
  it("renders header + regime badge + strategy title from a fixture", () => {
    render(<DailyDecisionCard decision={fixture()} />);

    expect(screen.getByTestId("daily-decision-card")).toBeInTheDocument();
    expect(screen.getByTestId("decision-header")).toHaveTextContent("MSFT");
    expect(screen.getByTestId("market-state-badge").getAttribute("data-regime")).toBe(
      "HIGH_IV_PIN",
    );
    expect(screen.getByTestId("strategy-title")).toHaveTextContent(
      "Sell Partial Covered Call",
    );
  });

  it("renders all live sections (M1.19/M1.20/M1.21) with no placeholders remaining", () => {
    render(<DailyDecisionCard decision={fixture()} />);
    // M1.19: live action list.
    expect(screen.getByTestId("action-list")).toBeInTheDocument();
    expect(screen.getByTestId("action-row-0")).toHaveTextContent(
      "Sell Partial Covered Call",
    );
    // M1.20: confidence chart + execution panel.
    expect(screen.getByTestId("confidence-chart")).toBeInTheDocument();
    expect(screen.getByTestId("execution-feasibility-panel")).toBeInTheDocument();
    // M1.21: Why/Risks/Invalidation drawer section.
    expect(screen.getByTestId("rationale-section")).toBeInTheDocument();
    expect(screen.getByTestId("drawer-why")).toHaveTextContent(
      "IV rank 78 favours selling premium",
    );
    // The Phase-1 component tree is complete — no placeholders remain.
    expect(screen.queryAllByTestId(/^placeholder-/)).toHaveLength(0);
  });

  it("falls back to NO_OP strategy when recommendation.actions is empty", () => {
    render(
      <DailyDecisionCard
        decision={fixture({ recommendation: { actions: [] } })}
      />,
    );
    expect(screen.getByTestId("strategy-title")).toHaveTextContent(
      "No Action Today",
    );
  });

  it("propagates regime + tags through to the badge", () => {
    render(
      <DailyDecisionCard
        decision={fixture({
          market_state: {
            regime: "BREAKOUT",
            regime_score: 0.95,
            tags: ["above_resistance"],
          },
        })}
      />,
    );
    const badge = screen.getByTestId("market-state-badge");
    expect(badge.getAttribute("data-regime")).toBe("BREAKOUT");
    expect(badge).toHaveTextContent("above_resistance");
  });

  it("surfaces decision_id + engine_version + weights_version in the footer", () => {
    render(<DailyDecisionCard decision={fixture()} />);
    const footer = screen.getByTestId("decision-footer");
    expect(footer).toHaveTextContent("dd_a1b2c3d4e5f6_1748530200");
    expect(footer).toHaveTextContent("engine v1.4.0");
    expect(footer).toHaveTextContent("weights v2.0");
  });

  it("propagates data_freshness.any_stale=true to the freshness badge", () => {
    render(
      <DailyDecisionCard
        decision={fixture({
          data_freshness: { any_stale: true, stale_tags: ["stale_iv"] },
        })}
      />,
    );
    expect(screen.getByTestId("freshness-stale-badge")).toBeInTheDocument();
  });
});
