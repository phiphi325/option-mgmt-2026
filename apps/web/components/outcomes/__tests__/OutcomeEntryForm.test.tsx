import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

import { OutcomeEntryForm } from "../OutcomeEntryForm";
import type { Outcome } from "@/lib/outcome-types";

const { createMock } = vi.hoisted(() => ({ createMock: vi.fn() }));
vi.mock("@/app/outcomes/actions", () => ({
  createOutcomeAction: createMock,
}));

const CREATED: Outcome = {
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

const DECISION_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";

beforeEach(() => {
  createMock.mockReset();
  createMock.mockResolvedValue({ ok: true, outcome: CREATED });
});

describe("OutcomeEntryForm", () => {
  it("keeps Save disabled until a decision id is entered", () => {
    render(<OutcomeEntryForm onCreated={() => {}} />);
    const save = screen.getByTestId<HTMLButtonElement>("entry-save-button");
    expect(save.disabled).toBe(true);

    fireEvent.change(screen.getByTestId("field-new-daily_decision_id"), {
      target: { value: DECISION_ID },
    });
    expect(save.disabled).toBe(false);
  });

  it("maps the form to a create body (\"\"→null, defaults) and calls the action", () => {
    render(<OutcomeEntryForm onCreated={() => {}} />);

    fireEvent.change(screen.getByTestId("field-new-daily_decision_id"), {
      target: { value: DECISION_ID },
    });
    fireEvent.change(screen.getByTestId("field-new-decision_quality"), {
      target: { value: "good" },
    });
    fireEvent.change(screen.getByTestId("field-new-pnl_realized"), {
      target: { value: "1250.00" },
    });
    fireEvent.submit(screen.getByTestId("outcome-entry-form"));

    expect(createMock).toHaveBeenCalledTimes(1);
    expect(createMock).toHaveBeenCalledWith({
      daily_decision_id: DECISION_ID,
      horizon_days: 7,
      pnl_realized: "1250.00",
      pnl_unrealized: null,
      decision_quality: "good",
      error_type: "none",
      actual_regime_realized: null,
      regime_match: null,
      notes: null,
    });
  });

  it("reports success and resets the decision id after a create", async () => {
    const onCreated = vi.fn();
    render(<OutcomeEntryForm onCreated={onCreated} />);

    fireEvent.change(screen.getByTestId("field-new-daily_decision_id"), {
      target: { value: DECISION_ID },
    });
    fireEvent.submit(screen.getByTestId("outcome-entry-form"));

    await waitFor(() =>
      expect(screen.getByTestId("entry-status")).toHaveTextContent(/recorded/i),
    );
    expect(onCreated).toHaveBeenCalledWith(CREATED);
    expect(
      screen.getByTestId<HTMLInputElement>("field-new-daily_decision_id").value,
    ).toBe("");
  });

  it("surfaces the error message when the create fails", async () => {
    createMock.mockResolvedValue({
      ok: false,
      error: "outcome already exists for this daily_decision_id",
    });
    render(<OutcomeEntryForm onCreated={() => {}} />);

    fireEvent.change(screen.getByTestId("field-new-daily_decision_id"), {
      target: { value: DECISION_ID },
    });
    fireEvent.submit(screen.getByTestId("outcome-entry-form"));

    await waitFor(() =>
      expect(screen.getByTestId("entry-status")).toHaveTextContent(
        "outcome already exists for this daily_decision_id",
      ),
    );
  });
});
