import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { MarketStateBadge } from "../MarketStateBadge";

describe("MarketStateBadge", () => {
  it.each([
    ["HIGH_IV_EVENT", "amber", "High IV — Event Window"],
    ["HIGH_IV_PIN", "slate", "High IV — Pin Risk"],
    ["LOW_IV_TREND", "emerald", "Low IV — Trending"],
    ["LOW_IV_RANGE", "sky", "Low IV — Range-Bound"],
    ["BREAKOUT", "violet", "Breakout"],
    ["POST_EVENT_REPRICE", "rose", "Post-Event Reprice"],
  ] as const)(
    "renders %s with %s color tokens + correct label",
    (regime, tokenStem, label) => {
      render(<MarketStateBadge regime={regime} />);
      const badge = screen.getByTestId("market-state-badge");
      expect(badge.getAttribute("data-regime")).toBe(regime);
      // Tailwind class fragment for the regime's color stem
      expect(badge.className).toContain(`bg-${tokenStem}-100`);
      expect(badge.className).toContain(`text-${tokenStem}-900`);
      expect(badge).toHaveTextContent(label);
    },
  );

  it("includes regime label as text (not color-only encoding) per §8 accessibility", () => {
    render(<MarketStateBadge regime="HIGH_IV_PIN" />);
    const badge = screen.getByTestId("market-state-badge");
    // The visible text includes the regime, so screen readers see it too.
    expect(badge.textContent).toMatch(/High IV/i);
    // aria-label restates the regime
    expect(badge).toHaveAttribute("aria-label", expect.stringMatching(/Pin Risk/i));
  });

  it("renders tags as a comma-separated subtitle when present", () => {
    render(
      <MarketStateBadge
        regime="HIGH_IV_PIN"
        tags={["sell_vol_favorable", "near_opex"]}
      />,
    );
    const badge = screen.getByTestId("market-state-badge");
    expect(badge).toHaveTextContent("sell_vol_favorable, near_opex");
  });

  it("omits the tags subtitle when tags is empty or undefined", () => {
    render(<MarketStateBadge regime="HIGH_IV_PIN" tags={[]} />);
    const badge = screen.getByTestId("market-state-badge");
    expect(badge.textContent).not.toContain(",");
  });
});
