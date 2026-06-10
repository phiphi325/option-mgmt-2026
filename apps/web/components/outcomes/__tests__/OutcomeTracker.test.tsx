import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { OutcomeTracker } from "../OutcomeTracker";
import type { Outcome } from "@/lib/outcome-types";

const { createMock, patchMock, loadMoreMock } = vi.hoisted(() => ({
  createMock: vi.fn(),
  patchMock: vi.fn(),
  loadMoreMock: vi.fn(),
}));
vi.mock("@/app/outcomes/actions", () => ({
  createOutcomeAction: createMock,
  patchOutcomeAction: patchMock,
  loadMoreOutcomesAction: loadMoreMock,
}));

function makeOutcome(id: string, ddId: string): Outcome {
  return {
    id,
    daily_decision_id: ddId,
    evaluated_at: "2026-06-01T12:00:00Z",
    horizon_days: 7,
    pnl_realized: null,
    pnl_unrealized: null,
    decision_quality: "neutral",
    error_type: "none",
    actual_regime_realized: null,
    regime_match: null,
    notes: null,
    source: "manual",
  };
}

const A = makeOutcome("aaaa1111-0000-0000-0000-000000000000", "dd-a");
const B = makeOutcome("bbbb2222-0000-0000-0000-000000000000", "dd-b");
const C = makeOutcome("cccc3333-0000-0000-0000-000000000000", "dd-c");

beforeEach(() => {
  createMock.mockReset();
  patchMock.mockReset();
  loadMoreMock.mockReset();
});

describe("OutcomeTracker", () => {
  it("prepends a newly created outcome to the history", async () => {
    createMock.mockResolvedValue({ ok: true, outcome: B });
    render(<OutcomeTracker initialOutcomes={[A]} initialCursor={null} />);

    fireEvent.change(screen.getByTestId("field-new-daily_decision_id"), {
      target: { value: "dd-b" },
    });
    fireEvent.submit(screen.getByTestId("outcome-entry-form"));

    await screen.findByTestId(`outcome-row-${B.id}`);
    // Prepend: B is the first row in the table.
    expect(
      screen.getByTestId("outcome-table").firstElementChild?.getAttribute(
        "data-testid",
      ),
    ).toBe(`outcome-row-${B.id}`);
    expect(screen.getByTestId(`outcome-row-${A.id}`)).toBeInTheDocument();
  });

  it("appends the next cursor page and hides Load more when exhausted", async () => {
    loadMoreMock.mockResolvedValue({ ok: true, outcomes: [C], nextCursor: null });
    render(<OutcomeTracker initialOutcomes={[A]} initialCursor={"cur1"} />);

    fireEvent.click(screen.getByTestId("load-more-button"));

    await screen.findByTestId(`outcome-row-${C.id}`);
    expect(loadMoreMock).toHaveBeenCalledWith("cur1");
    expect(screen.queryByTestId("load-more-button")).toBeNull();
  });

  it("shows no Load more when there is no initial cursor", () => {
    render(<OutcomeTracker initialOutcomes={[A]} initialCursor={null} />);
    expect(screen.queryByTestId("load-more-button")).toBeNull();
  });
});
