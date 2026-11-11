import { afterEach, describe, expect, it, vi } from "vitest";
import { scrollBehaviour } from "./motion.js";

function preferReducedMotion(reduce: boolean): void {
  vi.stubGlobal(
    "matchMedia",
    (query: string) =>
      ({ matches: reduce && query === "(prefers-reduced-motion: reduce)", media: query }) as MediaQueryList,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("scrollBehaviour", () => {
  it("scrolls smoothly, unless the person has asked for less motion", () => {
    preferReducedMotion(false);
    expect(scrollBehaviour()).toBe("smooth");
    preferReducedMotion(true);
    expect(scrollBehaviour()).toBe("auto");
  });
});
