import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { DecisionHeader } from "../DecisionHeader";

const _baseFreshness = { any_stale: false };

describe("DecisionHeader", () => {
  it("renders ticker, spot, and as-of label", () => {
    render(
      <DecisionHeader
        ticker="MSFT"
        spot={415.0}
        asOf="2026-05-20T14:30:00Z"
        dataFreshness={_baseFreshness}
      />,
    );
    expect(screen.getByText("MSFT")).toBeInTheDocument();
    expect(screen.getByTestId("spot")).toHaveTextContent("$415.00");
    expect(screen.getByTestId("as-of").textContent).toMatch(/as of /);
  });

  it("omits the freshness badge when any_stale is false", () => {
    render(
      <DecisionHeader
        ticker="MSFT"
        spot={415}
        asOf="2026-05-20T14:30:00Z"
        dataFreshness={{ any_stale: false }}
      />,
    );
    expect(screen.queryByTestId("freshness-stale-badge")).not.toBeInTheDocument();
  });

  it("shows the freshness badge when any_stale is true", () => {
    render(
      <DecisionHeader
        ticker="MSFT"
        spot={415}
        asOf="2026-05-20T14:30:00Z"
        dataFreshness={{ any_stale: true, stale_tags: ["stale_chain"] }}
      />,
    );
    const badge = screen.getByTestId("freshness-stale-badge");
    expect(badge).toBeInTheDocument();
    // Badge includes stale tag list in title attr (per spec)
    expect(badge.getAttribute("title")).toContain("stale_chain");
  });

  it("formats spot as currency with 2 decimals", () => {
    render(
      <DecisionHeader
        ticker="MSFT"
        spot={1234.5}
        asOf="2026-05-20T14:30:00Z"
        dataFreshness={_baseFreshness}
      />,
    );
    expect(screen.getByTestId("spot")).toHaveTextContent("$1,234.50");
  });

  it("falls back to the raw asOf string if Date parsing fails", () => {
    render(
      <DecisionHeader
        ticker="MSFT"
        spot={415}
        asOf="definitely-not-a-date"
        dataFreshness={_baseFreshness}
      />,
    );
    const asOf = screen.getByTestId("as-of");
    expect(asOf.getAttribute("title")).toBe("definitely-not-a-date");
  });
});
