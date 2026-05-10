import { describe, it, expect } from "vitest";
import { cn } from "@/lib/utils";

describe("cn", () => {
  it("joins string class names", () => {
    expect(cn("a", "b")).toBe("a b");
  });

  it("ignores falsy values", () => {
    expect(cn("a", false && "b", null, undefined, "c")).toBe("a c");
  });

  it("dedupes conflicting tailwind utilities (later wins)", () => {
    expect(cn("p-4", "p-2")).toBe("p-2");
  });

  it("merges arbitrary nested arrays/objects via clsx", () => {
    expect(cn(["a", { b: true, c: false }], "d")).toBe("a b d");
  });
});
