import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { ConfidenceBreakdownChart } from "../ConfidenceBreakdownChart";
import type { ConfidenceBreakdown } from "@/lib/decision-types";

function breakdown(overrides: Partial<ConfidenceBreakdown> = {}): ConfidenceBreakdown {
  return {
    flow_alignment: 0.8,
    structure_alignment: 0.7,
    regime_match: 0.9,
    signal_alignment: 0.75,
    event_risk_penalty: 0.1,
    illiquidity_penalty: 0.05,
    positive_score: 0.79,
    penalty_multiplier: 0.96,
    weights_version: "v2.0",
    ...overrides,
  };
}

describe("ConfidenceBreakdownChart", () => {
  it("shows the total confidence percentage prominently", () => {
    render(<ConfidenceBreakdownChart confidence={0.76} breakdown={breakdown()} />);
    expect(screen.getByTestId("confidence-chart")).toHaveTextContent("76%");
    expect(screen.getByLabelText("76 percent confidence")).toBeInTheDocument();
  });

  it("renders all six component legend entries with percentages", () => {
    render(<ConfidenceBreakdownChart confidence={0.76} breakdown={breakdown()} />);
    for (const key of [
      "flow_alignment",
      "structure_alignment",
      "regime_match",
      "signal_alignment",
      "event_risk_penalty",
      "illiquidity_penalty",
    ]) {
      expect(screen.getByTestId(`legend-${key}`)).toBeInTheDocument();
    }
    expect(screen.getByTestId("legend-flow_alignment")).toHaveTextContent("80%");
  });

  it("prefixes penalty components with a minus sign", () => {
    render(<ConfidenceBreakdownChart confidence={0.76} breakdown={breakdown()} />);
    expect(screen.getByTestId("legend-event_risk_penalty").textContent ?? "").toMatch(/[−-]10%/);
    expect(screen.getByTestId("legend-illiquidity_penalty").textContent ?? "").toMatch(/[−-]5%/);
    // Positive components must NOT carry a minus prefix.
    expect(screen.getByTestId("legend-flow_alignment").textContent ?? "").not.toMatch(/[−-]80%/);
  });

  it("renders the §22.13 arithmetic caption and weights version", () => {
    render(<ConfidenceBreakdownChart confidence={0.76} breakdown={breakdown()} />);
    const caption = screen.getByTestId("confidence-arithmetic");
    expect(caption).toHaveTextContent("79%");
    expect(caption).toHaveTextContent("0.96");
    expect(screen.getByTestId("confidence-chart")).toHaveTextContent("weights v2.0");
  });

  it("renders the stacked bar primitive", () => {
    render(<ConfidenceBreakdownChart confidence={0.76} breakdown={breakdown()} />);
    expect(screen.getByTestId("stacked-confidence-bar")).toBeInTheDocument();
  });

  it("falls back to a placeholder (but still shows the score) when breakdown is missing", () => {
    render(<ConfidenceBreakdownChart confidence={0.5} breakdown={null} />);
    expect(screen.getByTestId("confidence-chart-no-breakdown")).toBeInTheDocument();
    expect(screen.getByTestId("confidence-chart")).toHaveTextContent("50%");
    expect(screen.queryByTestId("stacked-confidence-bar")).toBeNull();
  });
});
