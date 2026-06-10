import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type {
  YearlineContext,
  YearlinePanelResponse,
  YearlineTrendSeries,
} from "@/lib/yearline-types";

import { YearlinePanel } from "../YearlinePanel";

const context: YearlineContext = {
  as_of: "2026-05-29",
  ticker: "MSFT",
  schema_version: "s",
  model_stack_version: "m",
  adapter_version: "v13_8_yearline_context_adapter_v1",
  repair_active: true,
  distance_to_ma250_pct: -2.967,
  required_rebound_to_ma250_pct: 3.06,
  post_confirmation_trend_state: null,
  p_retry: { "10": 0.54 },
  p_retry_basis: "blend",
  gate_passed: { "10": true },
  days_to_touch_central: 0,
  days_to_touch_low: 0,
  days_to_touch_high: 35,
  p_success: 0.13,
  success_gate_passed: true,
  p_successful_reclaim: { "10": 0.07 },
  reference_scope: "group_transition_state",
  is_stale: false,
  must_not_auto_execute: true,
};

const series: YearlineTrendSeries = {
  available: true,
  series_version: "v13_8_1_yearline_trend_series_v1",
  must_not_auto_execute: true,
  ticker: "MSFT",
  as_of: "2026-05-29",
  dates: ["2026-05-28", "2026-05-29"],
  distance_to_ma250_pct: [-3.0, -2.967],
};

describe("YearlinePanel", () => {
  it("renders the unavailable placeholder when both context and series are null", () => {
    const panel: YearlinePanelResponse = {
      ticker: "MSFT",
      context: null,
      trend_series: null,
    };
    render(<YearlinePanel panel={panel} />);
    expect(screen.getByTestId("yearline-panel-unavailable")).toHaveTextContent(
      /unavailable for MSFT/i,
    );
    expect(screen.queryByTestId("yearline-panel")).not.toBeInTheDocument();
  });

  it("renders the card + chart when data is present", () => {
    const panel: YearlinePanelResponse = {
      ticker: "MSFT",
      context,
      trend_series: series,
    };
    render(<YearlinePanel panel={panel} />);
    expect(screen.getByTestId("yearline-panel")).toBeInTheDocument();
    expect(screen.getByTestId("yearline-card")).toBeInTheDocument();
    expect(screen.getByTestId("yearline-trend-chart")).toBeInTheDocument();
  });

  it("renders the chart's empty state when the series is null", () => {
    const panel: YearlinePanelResponse = {
      ticker: "MSFT",
      context,
      trend_series: null,
    };
    render(<YearlinePanel panel={panel} />);
    expect(screen.getByTestId("yearline-card")).toBeInTheDocument();
    expect(screen.getByTestId("yearline-trend-empty")).toBeInTheDocument();
  });
});
