import { describe, expect, it } from "vitest";
import { autoScrollStep, EDGE_PX, MAX_STEP_PX } from "./dragScroll.js";

const box = { top: 100, bottom: 700 };

describe("autoScrollStep", () => {
  it("leaves the list be away from its edges", () => {
    expect(autoScrollStep(400, box)).toBe(0);
    expect(autoScrollStep(box.top + EDGE_PX, box)).toBe(0);
    expect(autoScrollStep(box.bottom - EDGE_PX, box)).toBe(0);
  });

  it("scrolls up near the top and down near the bottom, faster the nearer the edge", () => {
    expect(autoScrollStep(box.top + 30, box)).toBeLessThan(0);
    expect(autoScrollStep(box.top + 5, box)).toBeLessThan(autoScrollStep(box.top + 30, box));
    expect(autoScrollStep(box.bottom - 5, box)).toBeGreaterThan(autoScrollStep(box.bottom - 30, box));
    expect(autoScrollStep(box.bottom - 30, box)).toBeGreaterThan(0);
  });

  it("goes no faster than its top speed past the edge", () => {
    expect(autoScrollStep(box.top - 200, box)).toBe(-MAX_STEP_PX);
    expect(autoScrollStep(box.bottom + 200, box)).toBe(MAX_STEP_PX);
  });
});
