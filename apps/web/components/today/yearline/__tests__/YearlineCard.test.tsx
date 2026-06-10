import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { YearlineContext } from "@/lib/yearline-types";

import { YearlineCard } from "../YearlineCard";

const gated: YearlineContext = {
  as_of: "2026-05-29",
  ticker: "MSFT",
  schema_version: "v13_single_ticker_statistical_context_envelope",
  model_stack_version: "yearline_universe_v13.1",
  adapter_version: "v13_8_yearline_context_adapter_v1",
  repair_active: true,
  distance_to_ma250_pct: -2.967,
  required_rebound_to_ma250_pct: 3.0578,
  post_confirmation_trend_state: null,
  p_retry: { "10": 0.54, "20": 0.6477, "40": 0.8941, "60": 0.936 },
  p_retry_basis: "blend",
  gate_passed: { "10": true, "20": true, "40": true, "60": true },
  days_to_touch_central: 0,
  days_to_touch_low: 0,
  days_to_touch_high: 35.18,
  p_success: 0.1369,
  success_gate_passed: true,
  p_successful_reclaim: { "10": 0.0739, "20": 0.0887, "40": 0.1224, "60": 0.1281 },
  reference_scope: "group_transition_state",
  is_stale: false,
  must_not_auto_execute: true,
};

describe("YearlineCard", () => {
  it("renders the repair regime chip + gated retry bars", () => {
    render(<YearlineCard context={gated} />);
    expect(screen.getByTestId("yearline-regime-chip")).toHaveTextContent(
      "Repair / retry watch",
    );
    expect(screen.getByTestId("yearline-retry-bars")).toBeInTheDocument();
    expect(screen.getByTestId("yearline-card")).toHaveTextContent("54.0%");
  });

  it("shows 'withheld' for an ungated horizon, the number for a gated one", () => {
    const partial: YearlineContext = {
      ...gated,
      gate_passed: { "10": true, "20": false, "40": false, "60": false },
    };
    render(<YearlineCard context={partial} />);
    // gated 10d → number present
    expect(screen.getByTestId("yearline-card")).toHaveTextContent("54.0%");
    // ungated 20/40/60 → withheld, never the raw number
    expect(screen.getByTestId("yearline-retry-withheld-20")).toHaveTextContent(
      /withheld/i,
    );
    expect(screen.getByTestId("yearline-card")).not.toHaveTextContent("64.8%");
  });

  it("renders a stale badge when is_stale", () => {
    render(<YearlineCard context={{ ...gated, is_stale: true }} />);
    expect(screen.getByTestId("yearline-stale-badge")).toBeInTheDocument();
  });

  it("shows the trend state (not retry bars) when dormant above the yearline", () => {
    const dormant: YearlineContext = {
      ...gated,
      repair_active: false,
      p_retry: {},
      gate_passed: {},
      p_retry_basis: null,
      post_confirmation_trend_state: "pullback_but_intact",
    };
    render(<YearlineCard context={dormant} />);
    expect(screen.getByTestId("yearline-regime-chip")).toHaveTextContent(
      "Confirmed trend",
    );
    expect(screen.getByTestId("yearline-retry-dormant")).toHaveTextContent(
      "Pullback, trend intact",
    );
    expect(screen.queryByTestId("yearline-retry-bars")).not.toBeInTheDocument();
  });

  it("hides P(success) when the success gate is closed", () => {
    render(
      <YearlineCard
        context={{ ...gated, success_gate_passed: false }}
      />,
    );
    expect(screen.queryByTestId("yearline-success")).not.toBeInTheDocument();
  });
});
