import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { StrategyTitle } from "../StrategyTitle";

describe("StrategyTitle", () => {
  it("renders the human label for a known emit code", () => {
    render(<StrategyTitle strategy="SELL_COVERED_CALL_PARTIAL" />);
    expect(screen.getByTestId("strategy-title")).toHaveTextContent(
      "Sell Partial Covered Call",
    );
  });

  it.each([
    ["ROLL_UP_AND_OUT", "Roll Up and Out"],
    ["WHEEL_SHORT_PUT", "Wheel — Short Put"],
    ["BUY_LONG_DATED_PUT", "Buy Long-Dated Put"],
    ["OPEN_COLLAR", "Open Collar"],
    ["REDUCE_COVERAGE", "Reduce Coverage"],
    ["MONETIZE_PUT", "Monetize Put"],
    ["NO_OP", "No Action Today"],
  ])("maps %s → %s", (code, label) => {
    render(<StrategyTitle strategy={code} />);
    expect(screen.getByTestId("strategy-title")).toHaveTextContent(label);
  });

  it("falls back to humanized snake-case for unknown codes (no crash)", () => {
    render(<StrategyTitle strategy="FANCY_NEW_STRATEGY" />);
    expect(screen.getByTestId("strategy-title")).toHaveTextContent(
      "Fancy New Strategy",
    );
  });

  it("renders NO_OP label when strategy is null/undefined (defensive)", () => {
    render(<StrategyTitle strategy={null} />);
    expect(screen.getByTestId("strategy-title")).toHaveTextContent(
      "No Action Today",
    );
  });

  it("exposes the strategy code via data-strategy attr for analytics hooks", () => {
    render(<StrategyTitle strategy="BUY_LONG_DATED_PUT" />);
    const el = screen.getByTestId("strategy-title");
    expect(el.getAttribute("data-strategy")).toBe("BUY_LONG_DATED_PUT");
  });
});
