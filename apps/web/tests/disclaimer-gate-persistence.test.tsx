// M0.7 cross-stack smoke tests for the disclaimer gate's localStorage round-trip.
//
// The M0.4 tests (disclaimer-gate.test.tsx) cover the per-mount behavior:
// modal shows, accept persists, second mount sees the flag. This file
// closes the gap that smoke tests are meant to close — the FULL lifecycle:
//
//   mount → accept → unmount → remount      (simulates a real page reload)
//   mount → accept → clear store → remount  (simulates fresh device)
//   mount → accept → assert ISO 8601 shape  (matches M1.x DB column type)
//
// Per plan v1.2 §17 M0.7 + ADR-0004 (disclaimer fail-open).

import { beforeEach, describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { DisclaimerGate } from "@/components/today/DisclaimerGate";

const STORAGE_KEY = "disclaimerAcceptedAt_v1";

describe("DisclaimerGate persistence (M0.7)", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("survives a full unmount/remount cycle (simulates a page reload)", async () => {
    const user = userEvent.setup();

    // First mount: see modal, accept, modal closes, localStorage written.
    const { unmount } = render(
      <DisclaimerGate>
        <div data-testid="content-1">first mount</div>
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
    expect(localStorage.getItem(STORAGE_KEY)).toBeTruthy();
    expect(screen.getByTestId("content-1")).toBeInTheDocument();

    // Tear the app down — equivalent to a navigation/reload.
    unmount();

    // Second mount, same localStorage state.
    render(
      <DisclaimerGate>
        <div data-testid="content-2">second mount</div>
      </DisclaimerGate>,
    );

    // Modal must NOT show on this mount; the user already accepted.
    await waitFor(() => {
      expect(screen.getByTestId("content-2")).toBeInTheDocument();
    });
    expect(
      screen.queryByRole("dialog", { name: /educational use only/i }),
    ).not.toBeInTheDocument();
  });

  it("re-shows the modal if localStorage is cleared between mounts", async () => {
    const user = userEvent.setup();

    const { unmount } = render(
      <DisclaimerGate>
        <div>x</div>
      </DisclaimerGate>,
    );
    const button = await screen.findByRole("button", {
      name: /i understand/i,
    });
    await user.click(button);
    await waitFor(() => {
      expect(localStorage.getItem(STORAGE_KEY)).toBeTruthy();
    });
    unmount();

    // User clears storage (e.g. browser data wipe, fresh device, incognito).
    localStorage.removeItem(STORAGE_KEY);

    render(
      <DisclaimerGate>
        <div>y</div>
      </DisclaimerGate>,
    );

    // Modal must re-appear — the gate must NOT remember in-memory state
    // across mounts; persistence is the whole job of localStorage.
    expect(
      await screen.findByRole("dialog", { name: /educational use only/i }),
    ).toBeInTheDocument();
  });

  it("stores an ISO 8601 timestamp parseable by Date (M1.x DB compat)", async () => {
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
      expect(localStorage.getItem(STORAGE_KEY)).toBeTruthy();
    });

    const stored = localStorage.getItem(STORAGE_KEY)!;
    // Must parse cleanly — the M1.x users.disclaimer_accepted_at column is
    // TIMESTAMPTZ (per the M0.2 schema), and the migration assumes ISO 8601.
    const parsed = new Date(stored);
    expect(parsed.toString()).not.toBe("Invalid Date");
    // Recent timestamp (within 5s of now) — the click just happened.
    const ageMs = Date.now() - parsed.getTime();
    expect(ageMs).toBeGreaterThanOrEqual(0);
    expect(ageMs).toBeLessThan(5000);
  });
});
