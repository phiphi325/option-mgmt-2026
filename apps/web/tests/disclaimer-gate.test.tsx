import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { DisclaimerGate } from "@/components/today/DisclaimerGate";

describe("DisclaimerGate", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("renders the modal on first visit and blocks the children visually", async () => {
    render(
      <DisclaimerGate>
        <div data-testid="content">Today screen</div>
      </DisclaimerGate>,
    );

    // Children render so the gate sits *over* them rather than removing them
    // from the DOM (per plan: gate the disclaimer, don't replace the route).
    await waitFor(() => {
      expect(screen.getByTestId("content")).toBeInTheDocument();
    });

    expect(
      screen.getByRole("dialog", { name: /educational use only/i }),
    ).toBeInTheDocument();
  });

  it("hides the modal once the user accepts and persists to localStorage", async () => {
    const user = userEvent.setup();
    render(
      <DisclaimerGate>
        <div>x</div>
      </DisclaimerGate>,
    );

    const button = await screen.findByRole("button", {
      name: /i understand/i,
    });
    await user.click(button);

    await waitFor(() => {
      expect(
        screen.queryByRole("dialog", { name: /educational use only/i }),
      ).not.toBeInTheDocument();
    });

    expect(localStorage.getItem("disclaimerAcceptedAt_v1")).toBeTruthy();
  });

  it("does not show the modal on revisit when localStorage has the flag", async () => {
    localStorage.setItem("disclaimerAcceptedAt_v1", new Date().toISOString());

    render(
      <DisclaimerGate>
        <div>x</div>
      </DisclaimerGate>,
    );

    // After the effect runs, no dialog should be open.
    await waitFor(() => {
      expect(
        screen.queryByRole("dialog", { name: /educational use only/i }),
      ).not.toBeInTheDocument();
    });
  });

  it("fails open when localStorage throws (e.g. Safari private mode)", async () => {
    const setItemSpy = vi
      .spyOn(Storage.prototype, "setItem")
      .mockImplementation(() => {
        throw new Error("QuotaExceededError");
      });
    const getItemSpy = vi
      .spyOn(Storage.prototype, "getItem")
      .mockImplementation(() => {
        throw new Error("SecurityError");
      });

    render(
      <DisclaimerGate>
        <div data-testid="content">visible</div>
      </DisclaimerGate>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("content")).toBeInTheDocument();
    });
    // Modal should NOT block when storage is unavailable.
    expect(
      screen.queryByRole("dialog", { name: /educational use only/i }),
    ).not.toBeInTheDocument();

    setItemSpy.mockRestore();
    getItemSpy.mockRestore();
  });
});
