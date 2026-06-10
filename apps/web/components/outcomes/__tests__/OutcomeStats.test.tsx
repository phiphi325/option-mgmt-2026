import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { OutcomeStats } from "../OutcomeStats";
import type { Outcome } from "@/lib/outcome-types";

function makeOutcome(over: Partial<Outcome>): Outcome {
  return {
    id: `id-${Math.random()}`,
    daily_decision_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    evaluated_at: "2026-06-01T12:00:00Z",
    horizon_days: 7,
    pnl_realized: null,
    pnl_unrealized: null,
    decision_quality: null,
    error_type: "none",
    actual_regime_realized: null,
    regime_match: null,
    notes: null,
    source: "manual",
    ...over,
  };
}

const OUTCOMES: Outcome[] = [
  makeOutcome({ decision_quality: "good", error_type: "none" }),
  makeOutcome({ decision_quality: "good", error_type: "none" }),
  makeOutcome({ decision_quality: "bad", error_type: "early_roll" }),
  makeOutcome({ decision_quality: null, error_type: "none" }),
];

describe("OutcomeStats", () => {
  it("counts quality over the loaded rows", () => {
    render(<OutcomeStats outcomes={OUTCOMES} />);
    expect(screen.getByTestId("stats-quality-good")).toHaveTextContent("2");
    expect(screen.getByTestId("stats-quality-bad")).toHaveTextContent("1");
    expect(screen.getByTestId("stats-quality-neutral")).toHaveTextContent("0");
    expect(screen.getByTestId("stats-quality-unrated")).toHaveTextContent("1");
    expect(screen.getByTestId("stats-total")).toHaveTextContent("over 4 loaded");
  });

  it("renders an error-type histogram for present types", () => {
    render(<OutcomeStats outcomes={OUTCOMES} />);
    expect(screen.getByTestId("stats-error-none")).toHaveTextContent("3");
    expect(screen.getByTestId("stats-error-early_roll")).toHaveTextContent("1");
    expect(screen.queryByTestId("stats-error-wrong_strike")).toBeNull();
  });

  it("handles an empty list", () => {
    render(<OutcomeStats outcomes={[]} />);
    expect(screen.getByTestId("stats-total")).toHaveTextContent("over 0 loaded");
    expect(screen.getByTestId("stats-quality-good")).toHaveTextContent("0");
  });
});
