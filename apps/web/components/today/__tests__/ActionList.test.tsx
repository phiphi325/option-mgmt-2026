import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { ActionList } from "../ActionList";
import type { DailyDecision, Execution } from "@/lib/decision-types";

function baseDecision(overrides: Partial<DailyDecision> = {}): DailyDecision {
  return {
    decision_id: "dd_test",
    as_of: "2026-05-20T14:30:00Z",
    ticker: "MSFT",
    spot: 400,
    market_state: { regime: "HIGH_IV_PIN", regime_score: 0.7, tags: [] },
    flow_score: { score: 0.5, bias: "NEUTRAL", recommended_action: "WAIT" },
    recommendation: { actions: [] },
    confidence: 0.5,
    engine_version: "1.8.0",
    weights_version: "v2.0",
    inputs_hash: "sha256:deadbeef",
    data_freshness: { any_stale: false },
    ...overrides,
  };
}

const trivialExec: Execution = {
  aggregate_liquidity_score: 1,
  aggregate_fill_confidence: 1,
  suggested_order_type: "limit",
  legs: [],
  notes: [],
};

describe("ActionList", () => {
  it("renders the Hold state when there are no actions", () => {
    render(<ActionList decision={baseDecision({ recommendation: { actions: [] } })} />);
    expect(screen.getByTestId("action-list-no-op")).toHaveTextContent(
      "Hold — no action recommended today",
    );
    expect(screen.queryByTestId("action-list")).toBeNull();
  });

  it("renders the Hold state when the first action is NO_OP", () => {
    render(
      <ActionList
        decision={baseDecision({ recommendation: { actions: [{ emit: "NO_OP", parameters: {} }] } })}
      />,
    );
    expect(screen.getByTestId("action-list-no-op")).toBeInTheDocument();
  });

  it("renders one ActionRow per action", () => {
    render(
      <ActionList
        decision={baseDecision({
          recommendation: {
            actions: [
              { emit: "SELL_COVERED_CALL_PARTIAL", parameters: { strike: 420 } },
              { emit: "BUY_LONG_DATED_PUT", parameters: { strike: 360 } },
            ],
          },
          executions: [trivialExec, trivialExec],
        })}
      />,
    );
    expect(screen.getByTestId("action-list")).toBeInTheDocument();
    expect(screen.getByTestId("action-row-0")).toHaveTextContent("Sell Partial Covered Call");
    expect(screen.getByTestId("action-row-1")).toHaveTextContent("Buy Long-Dated Put");
  });

  it("passes the index-aligned collar_structures entry to the OPEN_COLLAR row", () => {
    render(
      <ActionList
        decision={baseDecision({
          recommendation: { actions: [{ emit: "OPEN_COLLAR", parameters: {} }] },
          executions: [trivialExec],
          collar_structures: [
            {
              name: "c", intent: "zero_cost", horizon_days: 45,
              long_put: { kind: "PUT", side: "BUY", strike: 380, expiry: "2026-07-17", qty: 50, delta: -0.25, iv: 0.22, bid: 3.95, ask: 4.05, mid: 4.0, premium: 4.0 },
              short_call: { kind: "CALL", side: "SELL", strike: 420, expiry: "2026-07-17", qty: 50, delta: 0.22, iv: 0.21, bid: 3.95, ask: 4.05, mid: 4.0, premium: -3.98 },
              net_debit_credit: -0.02, max_gain: 20, max_loss: -20,
              upside_breakeven: 420, downside_breakeven: 380,
              capped_upside_pct: 0.05, protected_downside_pct: 0.05, confidence: 0.7,
            },
          ],
        })}
      />,
    );
    expect(screen.getByTestId("collar-leg-put")).toHaveTextContent("$380.00");
    expect(screen.getByTestId("collar-leg-call")).toHaveTextContent("$420.00");
  });
});
