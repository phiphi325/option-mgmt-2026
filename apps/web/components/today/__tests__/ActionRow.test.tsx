import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { ActionRow } from "../ActionRow";
import type { Action, CollarStructure, Execution, ExecutionLeg } from "@/lib/decision-types";

function leg(overrides: Partial<ExecutionLeg> = {}): ExecutionLeg {
  return {
    leg_id: "leg",
    liquidity_score: 0.8,
    spread_bps: 10,
    fill_confidence: 0.85,
    expected_slippage: 0.02,
    suggested_order_type: "limit",
    limit_price_band: [1.0, 1.04],
    size_warnings: [],
    ...overrides,
  };
}

function execution(legs: ExecutionLeg[]): Execution {
  return {
    aggregate_liquidity_score: 0.8,
    aggregate_fill_confidence: 0.85,
    suggested_order_type: "limit",
    legs,
    notes: [],
  };
}

const collar: CollarStructure = {
  name: "Zero-cost 45d collar 380/420",
  intent: "zero_cost",
  horizon_days: 45,
  long_put: {
    kind: "PUT", side: "BUY", strike: 380, expiry: "2026-07-17",
    qty: 50, delta: -0.25, iv: 0.22, bid: 3.95, ask: 4.05, mid: 4.0, premium: 4.0,
  },
  short_call: {
    kind: "CALL", side: "SELL", strike: 420, expiry: "2026-07-17",
    qty: 50, delta: 0.22, iv: 0.21, bid: 3.95, ask: 4.05, mid: 4.0, premium: -3.98,
  },
  net_debit_credit: -0.02,
  max_gain: 20, max_loss: -20, upside_breakeven: 420, downside_breakeven: 380,
  capped_upside_pct: 0.05, protected_downside_pct: 0.05, confidence: 0.7,
};

describe("ActionRow", () => {
  it("renders a single-leg action's label and parameters", () => {
    const action: Action = { emit: "SELL_COVERED_CALL_PARTIAL", parameters: { strike: 420, qty: 5 } };
    render(<ActionRow action={action} execution={execution([leg()])} collarStructure={null} index={0} />);
    const row = screen.getByTestId("action-row-0");
    expect(row).toHaveTextContent("Sell Partial Covered Call");
    expect(row).toHaveTextContent("strike:");
    expect(row).toHaveTextContent("420");
    expect(row.getAttribute("data-emit")).toBe("SELL_COVERED_CALL_PARTIAL");
  });

  it("renders an ExecutionBadge when the execution has legs", () => {
    const action: Action = { emit: "SELL_COVERED_CALL_PARTIAL", parameters: {} };
    render(<ActionRow action={action} execution={execution([leg({ fill_confidence: 0.9 })])} collarStructure={null} index={0} />);
    expect(screen.getByTestId("execution-badge")).toHaveTextContent("90% fill");
  });

  it("omits the ExecutionBadge when there are no execution legs", () => {
    const action: Action = { emit: "MONETIZE_PUT", parameters: {} };
    render(<ActionRow action={action} execution={execution([])} collarStructure={null} index={0} />);
    expect(screen.queryByTestId("execution-badge")).toBeNull();
  });

  it("renders both collar legs and a net credit for OPEN_COLLAR", () => {
    const action: Action = { emit: "OPEN_COLLAR", parameters: {} };
    render(
      <ActionRow action={action} execution={execution([leg(), leg()])} collarStructure={collar} index={0} />,
    );
    const row = screen.getByTestId("action-row-0");
    expect(row).toHaveTextContent("Buy put");
    expect(row).toHaveTextContent("Sell call");
    expect(screen.getByTestId("collar-leg-put")).toHaveTextContent("$380.00");
    expect(screen.getByTestId("collar-leg-call")).toHaveTextContent("$420.00");
    // net_debit_credit -0.02 < 0 ⇒ a credit, shown as "$0.02 cr"
    expect(row).toHaveTextContent("Net credit");
    expect(row).toHaveTextContent("$0.02 cr");
  });

  it("does not render collar legs when collarStructure is null even if emit is OPEN_COLLAR", () => {
    const action: Action = { emit: "OPEN_COLLAR", parameters: { note: 1 } };
    render(<ActionRow action={action} execution={execution([])} collarStructure={null} index={2} />);
    expect(screen.queryByTestId("collar-leg-put")).toBeNull();
    expect(screen.getByTestId("action-row-2")).toHaveTextContent("Open Collar");
  });
});
