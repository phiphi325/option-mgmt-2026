import { describe, it, expect } from "vitest";

import {
  STRATEGY_LABELS,
  formatStrategy,
  humanizeSnakeCase,
} from "../strategy-labels";

describe("strategy-labels", () => {
  describe("STRATEGY_LABELS", () => {
    it("covers every M1.9 emit code from the dev spec", () => {
      // Per docs/phased-design/phase-1/m1.18-today-screen-scaffolding.md
      const required = [
        "SELL_COVERED_CALL_PARTIAL",
        "SELL_COVERED_CALL_AGGRESSIVE",
        "ROLL_UP_AND_OUT",
        "WHEEL_SHORT_PUT",
        "BUY_LONG_DATED_PUT",
        "OPEN_COLLAR",
        "REDUCE_COVERAGE",
        "MONETIZE_PUT",
        "NO_OP",
      ];
      for (const code of required) {
        expect(STRATEGY_LABELS[code]).toBeTruthy();
      }
    });

    it("does not contain ambiguous or duplicate labels", () => {
      const labels = Object.values(STRATEGY_LABELS);
      const unique = new Set(labels);
      expect(unique.size).toBe(labels.length);
    });
  });

  describe("humanizeSnakeCase", () => {
    it.each([
      ["SHORT_STRANGLE_SIZED", "Short Strangle Sized"],
      ["foo", "Foo"],
      ["FOO_BAR_BAZ", "Foo Bar Baz"],
      ["already words", "Already Words"],
      ["", ""],
    ])("%s -> %s", (input, expected) => {
      expect(humanizeSnakeCase(input)).toBe(expected);
    });
  });

  describe("formatStrategy", () => {
    it("returns the known label for a known emit code", () => {
      expect(formatStrategy("SELL_COVERED_CALL_PARTIAL")).toBe(
        "Sell Partial Covered Call",
      );
    });

    it("falls back to humanized snake-case for unknown codes", () => {
      expect(formatStrategy("FOO_BAR")).toBe("Foo Bar");
    });

    it("returns the NO_OP label for null / undefined / empty", () => {
      const noOp = STRATEGY_LABELS.NO_OP;
      expect(formatStrategy(null)).toBe(noOp);
      expect(formatStrategy(undefined)).toBe(noOp);
      expect(formatStrategy("")).toBe(noOp);
    });

    it("never throws on weird inputs (defensive)", () => {
      expect(() => formatStrategy("LITERAL_TYPO__")).not.toThrow();
      expect(() => formatStrategy("12345")).not.toThrow();
    });
  });
});
