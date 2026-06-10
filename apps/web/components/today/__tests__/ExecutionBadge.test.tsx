import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { ExecutionBadge } from "../ExecutionBadge";
import type { ExecutionLeg } from "@/lib/decision-types";

function makeLeg(overrides: Partial<ExecutionLeg> = {}): ExecutionLeg {
  return {
    leg_id: "SELL_CALL_420_2026-07-17",
    liquidity_score: 0.82,
    spread_bps: 12,
    fill_confidence: 0.87,
    expected_slippage: 0.03,
    suggested_order_type: "limit",
    limit_price_band: [2.98, 3.02],
    size_warnings: [],
    ...overrides,
  };
}

describe("ExecutionBadge", () => {
  it("renders fill% from fill_confidence and spread in bps", () => {
    render(<ExecutionBadge leg={makeLeg({ fill_confidence: 0.87, spread_bps: 12 })} />);
    const badge = screen.getByTestId("execution-badge");
    expect(badge).toHaveTextContent("87% fill");
    expect(badge).toHaveTextContent("12 bps");
    expect(badge.getAttribute("data-fill")).toBe("87");
  });

  it("uses the green (emerald) class for fill >= 80%", () => {
    render(<ExecutionBadge leg={makeLeg({ fill_confidence: 0.91 })} />);
    expect(screen.getByTestId("execution-badge").className).toContain("emerald");
  });

  it("uses the amber class for fill 60–79%", () => {
    render(<ExecutionBadge leg={makeLeg({ fill_confidence: 0.65 })} />);
    const cls = screen.getByTestId("execution-badge").className;
    expect(cls).toContain("amber");
    expect(cls).not.toContain("emerald");
  });

  it("uses the red (rose) class for fill < 60%", () => {
    render(<ExecutionBadge leg={makeLeg({ fill_confidence: 0.41 })} />);
    expect(screen.getByTestId("execution-badge").className).toContain("rose");
  });

  it("surfaces liquidity + order type + limit band via the title tooltip", () => {
    render(
      <ExecutionBadge
        leg={makeLeg({ liquidity_score: 0.82, suggested_order_type: "limit", limit_price_band: [2.98, 3.02] })}
      />,
    );
    const title = screen.getByTestId("execution-badge").getAttribute("title") ?? "";
    expect(title).toContain("Liquidity: 82%");
    expect(title).toContain("Order type: limit");
    expect(title).toContain("2.98–3.02");
  });

  it("shows a warning marker and includes warnings in the tooltip when present", () => {
    render(<ExecutionBadge leg={makeLeg({ size_warnings: ["qty exceeds 10% of OI"] })} />);
    expect(screen.getByTestId("execution-badge-warn")).toBeInTheDocument();
    expect(screen.getByTestId("execution-badge").getAttribute("title") ?? "").toContain(
      "qty exceeds 10% of OI",
    );
  });

  it("omits the warning marker when there are no size warnings", () => {
    render(<ExecutionBadge leg={makeLeg({ size_warnings: [] })} />);
    expect(screen.queryByTestId("execution-badge-warn")).toBeNull();
  });
});
