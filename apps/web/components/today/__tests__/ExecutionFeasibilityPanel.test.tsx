import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { ExecutionFeasibilityPanel } from "../ExecutionFeasibilityPanel";
import type { Execution } from "@/lib/decision-types";

function exec(overrides: Partial<Execution> = {}): Execution {
  return {
    aggregate_liquidity_score: 0.82,
    aggregate_fill_confidence: 0.85,
    suggested_order_type: "limit",
    legs: [],
    notes: [],
    ...overrides,
  };
}

describe("ExecutionFeasibilityPanel", () => {
  it("renders aggregate fill%, liquidity, and order type for the primary execution", () => {
    render(<ExecutionFeasibilityPanel executions={[exec({ aggregate_fill_confidence: 0.85, aggregate_liquidity_score: 0.82 })]} />);
    const panel = screen.getByTestId("execution-feasibility-panel");
    expect(panel).toHaveTextContent("85% fill");
    expect(panel).toHaveTextContent("Liquidity 82%");
    expect(panel).toHaveTextContent("Limit order");
  });

  it("uses the green (emerald) fill pill at >= 80%", () => {
    render(<ExecutionFeasibilityPanel executions={[exec({ aggregate_fill_confidence: 0.9 })]} />);
    expect(screen.getByTestId("execution-feasibility-fill").className).toContain("emerald");
  });

  it("uses the red (rose) fill pill at < 60%", () => {
    render(<ExecutionFeasibilityPanel executions={[exec({ aggregate_fill_confidence: 0.4 })]} />);
    expect(screen.getByTestId("execution-feasibility-fill").className).toContain("rose");
  });

  it("labels marketable_limit order type", () => {
    render(<ExecutionFeasibilityPanel executions={[exec({ suggested_order_type: "marketable_limit" })]} />);
    expect(screen.getByTestId("execution-feasibility-panel")).toHaveTextContent("Marketable limit");
  });

  it("renders notes when present and none when empty", () => {
    const { unmount } = render(
      <ExecutionFeasibilityPanel executions={[exec({ notes: ["aggregate fill below 0.50"] })]} />,
    );
    expect(screen.getByTestId("execution-feasibility-note")).toHaveTextContent(
      "aggregate fill below 0.50",
    );
    unmount();
    render(<ExecutionFeasibilityPanel executions={[exec({ notes: [] })]} />);
    expect(screen.queryByTestId("execution-feasibility-note")).toBeNull();
  });

  it("renders nothing when there are no executions", () => {
    const { container } = render(<ExecutionFeasibilityPanel executions={[]} />);
    expect(screen.queryByTestId("execution-feasibility-panel")).toBeNull();
    expect(container).toBeEmptyDOMElement();
  });
});
