/**
 * Tests for the Today error boundary's prerequisite-CTA mapping (M1.18).
 *
 * The component is a Next.js error boundary, but it's a regular client
 * component with `error` + `reset` props — so we can render it directly
 * with a fabricated error and assert the right CTA renders.
 *
 * Per the M1.18 dev spec: hydration 422s with `missing_chain` /
 * `missing_positions` / `insufficient_iv_history` tags surface as
 * friendly amber CTAs; everything else falls through to a generic
 * destructive error card.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import TodayError from "../error";

describe("TodayError boundary", () => {
  function makeError(message: string): Error {
    return new Error(message);
  }

  it("renders the missing_chain CTA when the error message mentions it", () => {
    const error = makeError("[422] Validation: missing_chain: no chain rows for MSFT");
    render(<TodayError error={error} reset={vi.fn()} />);
    const card = screen.getByTestId("prereq-error");
    expect(card.getAttribute("data-prereq-tag")).toBe("missing_chain");
    expect(card).toHaveTextContent(/option chain/i);
  });

  it("renders the missing_positions CTA", () => {
    const error = makeError("[422] missing_positions: no positions for MSFT");
    render(<TodayError error={error} reset={vi.fn()} />);
    const card = screen.getByTestId("prereq-error");
    expect(card.getAttribute("data-prereq-tag")).toBe("missing_positions");
    expect(card).toHaveTextContent(/positions/i);
  });

  it("renders the insufficient_iv_history CTA", () => {
    const error = makeError(
      "[422] insufficient_iv_history: ticker='MSFT' has 20 rows; need >= 30.",
    );
    render(<TodayError error={error} reset={vi.fn()} />);
    const card = screen.getByTestId("prereq-error");
    expect(card.getAttribute("data-prereq-tag")).toBe("insufficient_iv_history");
    expect(card).toHaveTextContent(/IV history/i);
  });

  it("renders the auth CTA when status is 401", () => {
    const error = makeError("[401] Not authenticated: Sign in to view");
    render(<TodayError error={error} reset={vi.fn()} />);
    expect(screen.getByTestId("auth-error")).toBeInTheDocument();
  });

  it("renders the generic error card for unrecognized errors", () => {
    const error = makeError("[500] Internal Server Error: unexpected bug");
    render(<TodayError error={error} reset={vi.fn()} />);
    expect(screen.getByTestId("generic-error")).toBeInTheDocument();
    expect(screen.getByTestId("generic-error")).toHaveTextContent(
      /Something went wrong/,
    );
  });
});
