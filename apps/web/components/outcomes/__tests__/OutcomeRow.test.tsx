import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

import { OutcomeRow } from "../OutcomeRow";
import type { Outcome } from "@/lib/outcome-types";

const { patchMock } = vi.hoisted(() => ({ patchMock: vi.fn() }));
vi.mock("@/app/outcomes/actions", () => ({
  patchOutcomeAction: patchMock,
}));

const ROW: Outcome = {
  id: "11111111-1111-1111-1111-111111111111",
  daily_decision_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  evaluated_at: "2026-06-01T12:00:00Z",
  horizon_days: 7,
  pnl_realized: "1250.00",
  pnl_unrealized: null,
  decision_quality: "good",
  error_type: "none",
  actual_regime_realized: null,
  regime_match: null,
  notes: null,
  source: "manual",
};

beforeEach(() => {
  patchMock.mockReset();
  patchMock.mockImplementation((_id: string, patch: Record<string, unknown>) =>
    Promise.resolve({ ok: true, outcome: { ...ROW, ...patch } }),
  );
});

describe("OutcomeRow", () => {
  it("renders the truncated decision id and formatted P&L (string wire form)", () => {
    render(<OutcomeRow outcome={ROW} onUpdated={() => {}} />);
    // The row shows the truncated daily_decision_id (not the outcome id).
    expect(screen.getByTestId(`row-decision-${ROW.id}`)).toHaveTextContent(
      "aaaaaaaa",
    );
    expect(screen.getByTestId(`row-pnl_realized-${ROW.id}`)).toHaveTextContent(
      "$1,250.00",
    );
  });

  it("renders a dash for null P&L", () => {
    render(
      <OutcomeRow
        outcome={{ ...ROW, pnl_realized: null }}
        onUpdated={() => {}}
      />,
    );
    expect(screen.getByTestId(`row-pnl_realized-${ROW.id}`)).toHaveTextContent(
      "—",
    );
  });

  it("edits inline and PATCHes the changed fields", async () => {
    const onUpdated = vi.fn();
    render(<OutcomeRow outcome={ROW} onUpdated={onUpdated} />);

    fireEvent.click(screen.getByTestId(`row-edit-${ROW.id}`));
    // Edit fields now present (namespaced by the outcome id).
    fireEvent.change(screen.getByTestId(`field-${ROW.id}-decision_quality`), {
      target: { value: "bad" },
    });
    fireEvent.click(screen.getByTestId(`row-save-${ROW.id}`));

    expect(patchMock).toHaveBeenCalledTimes(1);
    expect(patchMock).toHaveBeenCalledWith(ROW.id, {
      horizon_days: 7,
      pnl_realized: "1250.00",
      pnl_unrealized: null,
      decision_quality: "bad",
      error_type: "none",
      actual_regime_realized: null,
      regime_match: null,
      notes: null,
    });
    await waitFor(() => expect(onUpdated).toHaveBeenCalledTimes(1));
  });
});
