import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

import { UserStrategyProfileForm } from "../UserStrategyProfileForm";
import { PERSONAS } from "@/lib/personas";
import type { UserStrategyProfile } from "@/lib/decision-types";

// Mock the server action so the form never touches the network. `vi.hoisted`
// is required because `vi.mock` is hoisted above module-level `const`s.
const { saveProfileMock } = vi.hoisted(() => ({ saveProfileMock: vi.fn() }));
vi.mock("@/app/settings/actions", () => ({
  saveProfile: saveProfileMock,
}));

const INITIAL: UserStrategyProfile = {
  risk_tolerance: "moderate",
  income_need: "medium",
  max_position_pct: 0.5,
  max_coverage_pct: 0.75,
  min_iv_rank_for_short_premium: 40,
  prefer_collars_over_covered_calls: false,
  drawdown_tolerance: 0.15,
  style: "balanced",
};

beforeEach(() => {
  saveProfileMock.mockReset();
  // Default: succeed and echo the submitted profile (PUT is a full replace).
  saveProfileMock.mockImplementation((p: UserStrategyProfile) =>
    Promise.resolve({ ok: true, profile: p }),
  );
});

describe("UserStrategyProfileForm", () => {
  it("renders all eight fields seeded from initialProfile", () => {
    render(<UserStrategyProfileForm initialProfile={INITIAL} />);

    expect(
      screen.getByTestId<HTMLSelectElement>("field-risk_tolerance").value,
    ).toBe("moderate");
    expect(
      screen.getByTestId<HTMLSelectElement>("field-income_need").value,
    ).toBe("medium");
    expect(screen.getByTestId<HTMLSelectElement>("field-style").value).toBe(
      "balanced",
    );
    expect(
      screen.getByTestId<HTMLInputElement>("field-max_position_pct").value,
    ).toBe("0.5");
    expect(
      screen.getByTestId<HTMLInputElement>("field-max_coverage_pct").value,
    ).toBe("0.75");
    expect(
      screen.getByTestId<HTMLInputElement>(
        "field-min_iv_rank_for_short_premium",
      ).value,
    ).toBe("40");
    expect(
      screen.getByTestId<HTMLInputElement>("field-drawdown_tolerance").value,
    ).toBe("0.15");
    expect(
      screen.getByTestId<HTMLInputElement>(
        "field-prefer_collars_over_covered_calls",
      ).checked,
    ).toBe(false);
  });

  it("keeps Save disabled until a field changes", () => {
    render(<UserStrategyProfileForm initialProfile={INITIAL} />);
    const save = screen.getByTestId<HTMLButtonElement>("save-button");

    expect(save.disabled).toBe(true);
    fireEvent.change(screen.getByTestId("field-style"), {
      target: { value: "growth" },
    });
    expect(save.disabled).toBe(false);
  });

  it("submits the edited profile through the saveProfile action", async () => {
    render(<UserStrategyProfileForm initialProfile={INITIAL} />);

    fireEvent.change(screen.getByTestId("field-style"), {
      target: { value: "growth" },
    });
    fireEvent.submit(screen.getByTestId("profile-form"));

    expect(saveProfileMock).toHaveBeenCalledTimes(1);
    expect(saveProfileMock).toHaveBeenCalledWith({
      ...INITIAL,
      style: "growth",
    });
    await waitFor(() =>
      expect(screen.getByTestId("save-status")).toHaveTextContent(/saved/i),
    );
  });

  it("surfaces the error message when the save action fails", async () => {
    saveProfileMock.mockResolvedValue({
      ok: false,
      error: "min_iv_rank_for_short_premium must be <= 100",
    });
    render(<UserStrategyProfileForm initialProfile={INITIAL} />);

    fireEvent.change(
      screen.getByTestId("field-min_iv_rank_for_short_premium"),
      { target: { value: "70" } },
    );
    fireEvent.submit(screen.getByTestId("profile-form"));

    await waitFor(() =>
      expect(screen.getByTestId("save-status")).toHaveTextContent(
        "min_iv_rank_for_short_premium must be <= 100",
      ),
    );
  });

  it("restores the saved profile when Reset is clicked", () => {
    render(<UserStrategyProfileForm initialProfile={INITIAL} />);

    fireEvent.change(screen.getByTestId("field-style"), {
      target: { value: "growth" },
    });
    expect(screen.getByTestId<HTMLSelectElement>("field-style").value).toBe(
      "growth",
    );

    fireEvent.click(screen.getByTestId("reset-button"));

    expect(screen.getByTestId<HTMLSelectElement>("field-style").value).toBe(
      "balanced",
    );
    expect(
      screen.getByTestId<HTMLButtonElement>("save-button").disabled,
    ).toBe(true);
  });

  it("applies a persona preset into the form without saving", () => {
    render(<UserStrategyProfileForm initialProfile={INITIAL} />);

    fireEvent.click(screen.getByTestId("persona-ravi"));

    expect(
      screen.getByTestId<HTMLSelectElement>("field-risk_tolerance").value,
    ).toBe(PERSONAS.ravi.profile.risk_tolerance);
    expect(screen.getByTestId<HTMLSelectElement>("field-style").value).toBe(
      PERSONAS.ravi.profile.style,
    );
    expect(
      screen.getByTestId<HTMLInputElement>("field-max_coverage_pct").value,
    ).toBe(String(PERSONAS.ravi.profile.max_coverage_pct));

    // A preset fills but does not persist; Save becomes available for review.
    expect(saveProfileMock).not.toHaveBeenCalled();
    expect(
      screen.getByTestId<HTMLButtonElement>("save-button").disabled,
    ).toBe(false);
  });
});
