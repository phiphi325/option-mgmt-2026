import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { WatchLevels } from "../WatchLevels";

describe("WatchLevels", () => {
  it("renders above and below price levels with label and price", () => {
    render(
      <WatchLevels
        above={[{ price: 430, label: "max pain" }]}
        below={[{ price: 380, label: "support" }]}
        ivRankDropBelow={null}
      />,
    );
    const section = screen.getByTestId("watch-levels");
    expect(section).toHaveTextContent("$430");
    expect(section).toHaveTextContent("max pain");
    expect(section).toHaveTextContent("$380");
    expect(section).toHaveTextContent("support");
  });

  it("renders the IV-rank drop threshold when non-null", () => {
    render(<WatchLevels above={[]} below={[]} ivRankDropBelow={35} />);
    expect(screen.getByTestId("watch-levels-iv")).toHaveTextContent("IV rank drop < 35");
  });

  it("omits the IV pill when ivRankDropBelow is null", () => {
    render(<WatchLevels above={[{ price: 430, label: "max pain" }]} below={[]} ivRankDropBelow={null} />);
    expect(screen.queryByTestId("watch-levels-iv")).toBeNull();
  });

  it("renders nothing when there are no levels and no IV threshold", () => {
    const { container } = render(<WatchLevels above={[]} below={[]} ivRankDropBelow={null} />);
    expect(screen.queryByTestId("watch-levels")).toBeNull();
    expect(container).toBeEmptyDOMElement();
  });
});
