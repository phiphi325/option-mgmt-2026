import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { RationaleDrawer } from "../RationaleDrawer";
import { RisksDrawer } from "../RisksDrawer";
import { InvalidationDrawer } from "../InvalidationDrawer";

describe("RationaleDrawer", () => {
  it("renders the label in the summary and all item bullets", () => {
    render(<RationaleDrawer label="Why" items={["reason A", "reason B"]} />);
    expect(screen.getByTestId("drawer-trigger-why")).toHaveTextContent("Why");
    const content = screen.getByTestId("drawer-content-why");
    expect(content).toHaveTextContent("reason A");
    expect(content).toHaveTextContent("reason B");
    expect(content.querySelectorAll("li")).toHaveLength(2);
  });

  it("is collapsed by default (no `open` attribute)", () => {
    render(<RationaleDrawer label="Risks" items={["risk A"]} />);
    expect(screen.getByTestId("drawer-risks").hasAttribute("open")).toBe(false);
  });

  it("is expanded when defaultOpen is set (`open` attribute present)", () => {
    render(<RationaleDrawer label="Why" items={["reason A"]} defaultOpen />);
    expect(screen.getByTestId("drawer-why").hasAttribute("open")).toBe(true);
  });

  it("renders nothing when items is empty", () => {
    const { container } = render(<RationaleDrawer label="Why" items={[]} />);
    expect(screen.queryByTestId("drawer-why")).toBeNull();
    expect(container).toBeEmptyDOMElement();
  });

  it("slugifies multi-word labels for stable testids", () => {
    render(<RationaleDrawer label="What invalidates this?" items={["x"]} />);
    expect(screen.getByTestId("drawer-what-invalidates-this")).toBeInTheDocument();
    expect(screen.getByTestId("drawer-trigger-what-invalidates-this")).toBeInTheDocument();
  });
});

describe("RisksDrawer / InvalidationDrawer wrappers", () => {
  it("RisksDrawer renders the Risks label", () => {
    render(<RisksDrawer items={["risk A"]} />);
    expect(screen.getByTestId("drawer-trigger-risks")).toHaveTextContent("Risks");
  });

  it("InvalidationDrawer renders the invalidation label", () => {
    render(<InvalidationDrawer items={["invalidation A"]} />);
    expect(screen.getByTestId("drawer-trigger-what-invalidates-this")).toHaveTextContent(
      "What invalidates this?",
    );
  });

  it("both render nothing when items is empty", () => {
    const { container: c1 } = render(<RisksDrawer items={[]} />);
    expect(c1).toBeEmptyDOMElement();
    const { container: c2 } = render(<InvalidationDrawer items={[]} />);
    expect(c2).toBeEmptyDOMElement();
  });
});
