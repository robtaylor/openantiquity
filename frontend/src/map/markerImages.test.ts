// @vitest-environment node
import { describe, expect, it } from "vitest";
import { squareSdf } from "./markerImages.js";

describe("squareSdf", () => {
  const image = squareSdf();
  const alpha = (x: number, y: number): number => image.data[(y * 32 + x) * 4 + 3] as number;

  it("has the size MapLibre is told", () => {
    expect(image.width).toBe(32);
    expect(image.height).toBe(32);
    expect(image.data).toHaveLength(32 * 32 * 4);
  });

  it("crosses 0.75 at the edge of the square", () => {
    const edge = 0.75 * 255;
    // The square spans pixels 8 to 23. Just inside is above the edge value, just outside is below.
    expect(alpha(8, 16)).toBeGreaterThan(edge);
    expect(alpha(7, 16)).toBeLessThan(edge);
    expect(alpha(23, 16)).toBeGreaterThan(edge);
    expect(alpha(24, 16)).toBeLessThan(edge);
    expect(alpha(16, 8)).toBeGreaterThan(edge);
    expect(alpha(16, 7)).toBeLessThan(edge);
  });

  it("is solid in the middle and falls away to nothing", () => {
    expect(alpha(16, 16)).toBe(255);
    expect(alpha(0, 0)).toBe(0);
    expect(alpha(4, 16)).toBeLessThan(alpha(6, 16));
  });

  it("is symmetrical", () => {
    for (const [x, y] of [
      [3, 9],
      [10, 2],
      [12, 14],
    ] as const) {
      expect(alpha(x, y)).toBe(alpha(31 - x, y));
      expect(alpha(x, y)).toBe(alpha(x, 31 - y));
      expect(alpha(x, y)).toBe(alpha(y, x));
    }
  });
});
