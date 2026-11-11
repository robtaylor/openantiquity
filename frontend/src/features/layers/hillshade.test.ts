import { describe, expect, it } from "vitest";
import { hillshade, terrariumHeights } from "./hillshade.js";

/** A 5 by 5 grid rising one metre per cell in the direction given. */
function ramp(direction: "east" | "north"): Float32Array {
  const heights = new Float32Array(25);
  for (let y = 0; y < 5; y++) {
    for (let x = 0; x < 5; x++) heights[y * 5 + x] = direction === "east" ? x : 4 - y;
  }
  return heights;
}

function centre(pixels: Uint8ClampedArray): number {
  return pixels[12] ?? Number.NaN;
}

describe("terrariumHeights", () => {
  it("reads metres from red, green and blue", () => {
    // 128 × 256 + 10 + 128 / 256 − 32768 = 10.5
    expect(Array.from(terrariumHeights(new Uint8ClampedArray([128, 10, 128, 255]), 1, 1))).toEqual([10.5]);
  });

  it("refuses a buffer of the wrong size", () => {
    expect(() => terrariumHeights(new Uint8ClampedArray(4), 2, 2)).toThrow();
  });
});

describe("hillshade", () => {
  const light = { altitude: 20, exaggeration: 1 };

  it("draws level ground mid-grey whatever the sun's height", () => {
    for (const altitude of [10, 25, 60]) {
      const pixels = hillshade(new Float32Array(25), 5, 5, 1, { azimuth: 315, altitude, exaggeration: 1 });
      expect(centre(pixels)).toBe(128);
    }
  });

  it("lights a slope that faces the sun and darkens one that faces away", () => {
    const eastward = ramp("east");
    // The ground rises to the east, so it faces west.
    expect(centre(hillshade(eastward, 5, 5, 1, { ...light, azimuth: 270 }))).toBeGreaterThan(128);
    expect(centre(hillshade(eastward, 5, 5, 1, { ...light, azimuth: 90 }))).toBeLessThan(128);
    // Rising to the north, it faces south.
    const northward = ramp("north");
    expect(centre(hillshade(northward, 5, 5, 1, { ...light, azimuth: 180 }))).toBeGreaterThan(128);
    expect(centre(hillshade(northward, 5, 5, 1, { ...light, azimuth: 0 }))).toBeLessThan(128);
  });

  it("shows more contrast with more exaggeration", () => {
    const eastward = ramp("east");
    const gentle = centre(hillshade(eastward, 5, 5, 10, { ...light, azimuth: 270 }));
    const strong = centre(hillshade(eastward, 5, 5, 10, { ...light, azimuth: 270, exaggeration: 4 }));
    expect(strong).toBeGreaterThan(gentle);
  });
});
