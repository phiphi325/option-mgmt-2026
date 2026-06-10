import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { PersonaPresetButtons } from "../PersonaPresetButtons";
import { PERSONAS } from "@/lib/personas";

describe("PersonaPresetButtons", () => {
  it("renders a button for each of the three personas", () => {
    render(<PersonaPresetButtons onSelect={() => {}} />);
    expect(screen.getByTestId("persona-helen")).toHaveTextContent("Helen");
    expect(screen.getByTestId("persona-ravi")).toHaveTextContent("Ravi");
    expect(screen.getByTestId("persona-diana")).toHaveTextContent("Diana");
  });

  it("calls onSelect with the persona's full profile when clicked", () => {
    const onSelect = vi.fn();
    render(<PersonaPresetButtons onSelect={onSelect} />);

    fireEvent.click(screen.getByTestId("persona-ravi"));

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith(PERSONAS.ravi.profile);
  });

  it("exposes each persona description via a native title tooltip", () => {
    render(<PersonaPresetButtons onSelect={() => {}} />);
    expect(screen.getByTestId("persona-helen")).toHaveAttribute(
      "title",
      PERSONAS.helen.description,
    );
    expect(screen.getByTestId("persona-diana")).toHaveAttribute(
      "title",
      PERSONAS.diana.description,
    );
  });
});
