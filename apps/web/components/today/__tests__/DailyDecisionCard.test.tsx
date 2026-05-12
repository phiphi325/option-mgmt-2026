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
    },
    confidence: 0.62,
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

  it("renders three placeholder cards for M1.19/M1.20/M1.21", () => {
    render(<DailyDecisionCard decision={fixture()} />);
    expect(screen.getByTestId("placeholder-M1.19")).toBeInTheDocument();
    expect(screen.getByTestId("placeholder-M1.20")).toBeInTheDocument();
    expect(screen.getByTestId("placeholder-M1.21")).toBeInTheDocument();
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
