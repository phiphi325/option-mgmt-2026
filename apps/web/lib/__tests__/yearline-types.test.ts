import { describe, expect, it } from "vitest";

import { type YearlineTrendSeries, toDistancePoints } from "../yearline-types";

const base: YearlineTrendSeries = {
  available: true,
  series_version: "v13_8_1_yearline_trend_series_v1",
  must_not_auto_execute: true,
  ticker: "MSFT",
  as_of: "2026-05-29",
  dates: ["2026-05-26", "2026-05-27", "2026-05-28"],
  distance_to_ma250_pct: [-3.1, null, -2.9],
};

describe("toDistancePoints", () => {
  it("aligns dates to distances and preserves nulls as gaps", () => {
    const points = toDistancePoints(base);
    expect(points).toEqual([
      { date: "2026-05-26", distance: -3.1 },
      { date: "2026-05-27", distance: null }, // gap, not interpolated/zeroed
      { date: "2026-05-28", distance: -2.9 },
    ]);
  });

  it("returns [] for a null series", () => {
    expect(toDistancePoints(null)).toEqual([]);
  });

  it("returns [] for an unavailable series", () => {
    expect(
      toDistancePoints({ ...base, available: false }),
    ).toEqual([]);
  });

  it("pads missing distance entries as null gaps", () => {
    const points = toDistancePoints({
      ...base,
      distance_to_ma250_pct: [-3.1], // shorter than dates
    });
    expect(points.map((p) => p.distance)).toEqual([-3.1, null, null]);
  });
});
