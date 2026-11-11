import { describe, expect, it } from "vitest";
import {
  distanceM,
  distanceText,
  framingFor,
  LINE_PARAM,
  lineLengthM,
  MAX_LINE_POINTS,
  nearestIndex,
  PROFILE_PATH,
  parseLine,
  profilePath,
  sampleCount,
} from "./line.js";

describe("profilePath and parseLine", () => {
  it("write a line into the address and read it back to five places", () => {
    const path = profilePath([
      [-1.854201234, 51.4286],
      [-1.85, 51.43],
    ]);
    expect(path).toBe("/profile?line=-1.8542,51.4286,-1.85,51.43");
    const value = new URL(path, "http://localhost").searchParams.get(LINE_PARAM);
    expect(parseLine(value)).toEqual([
      [-1.8542, 51.4286],
      [-1.85, 51.43],
    ]);
  });

  it("leave the address bare for an empty line", () => {
    expect(profilePath([])).toBe(PROFILE_PATH);
    expect(parseLine(null)).toEqual([]);
    expect(parseLine("")).toEqual([]);
  });

  it("give an empty line for a damaged one rather than a wrong one", () => {
    expect(parseLine("-1.85,51.42,-1.86")).toEqual([]);
    expect(parseLine("-1.85,51.42,abc,51.43")).toEqual([]);
    expect(parseLine("-1.85,51.42,,51.43")).toEqual([]);
    expect(parseLine("-1.85,91,-1.86,51.43")).toEqual([]);
  });

  it("keep no more points than the server takes", () => {
    const many = Array.from({ length: MAX_LINE_POINTS + 5 }, (_, i) => `${-1.8 - i / 1000},51.4`).join(",");
    expect(parseLine(many)).toHaveLength(MAX_LINE_POINTS);
  });
});

describe("distances", () => {
  it("measure a degree of latitude as about 111 km", () => {
    expect(distanceM([0, 51], [0, 52])).toBeCloseTo(111_195, -2);
  });

  it("add up the legs of a line", () => {
    const line: Array<[number, number]> = [
      [0, 51],
      [0, 51.001],
      [0, 51.002],
    ];
    expect(lineLengthM(line)).toBeCloseTo(2 * distanceM([0, 51], [0, 51.001]), 6);
    expect(lineLengthM([[0, 51]])).toBe(0);
  });

  it("ask for about a sample a metre, within the server's limits", () => {
    expect(sampleCount(0)).toBe(2);
    expect(sampleCount(Number.NaN)).toBe(2);
    expect(sampleCount(120.2)).toBe(122);
    expect(sampleCount(4800)).toBe(1000);
  });

  it("say distances in metres, then kilometres", () => {
    expect(distanceText(12.4)).toBe("12 m");
    expect(distanceText(999)).toBe("999 m");
    expect(distanceText(1234)).toBe("1.23 km");
  });
});

describe("nearestIndex", () => {
  const points = [
    { x: 0, y: 0 },
    { x: 10, y: 0 },
    { x: 20, y: 0 },
  ];

  it("finds the nearest point within reach", () => {
    expect(nearestIndex(points, { x: 12, y: 3 }, 8)).toBe(1);
  });

  it("finds nothing out of reach", () => {
    expect(nearestIndex(points, { x: 10, y: 30 }, 8)).toBeNull();
    expect(nearestIndex([], { x: 0, y: 0 }, 8)).toBeNull();
  });
});

describe("framingFor", () => {
  it("centres on the line and zooms so it fills about half the map", () => {
    const framing = framingFor(
      [
        [-1.853, 51.4286],
        [-1.849, 51.4286],
      ],
      1000,
      800,
    );
    expect(framing?.lng).toBeCloseTo(-1.851, 6);
    expect(framing?.lat).toBeCloseTo(51.4286, 6);
    // 0.004 degrees is 500 px at zoom log2(500 / (0.004 / 360 * 512)).
    expect(framing?.zoom).toBeCloseTo(Math.log2(500 / ((0.004 / 360) * 512)), 6);
  });

  it("stops at a sensible zoom for a single point, and gives nothing for no line", () => {
    expect(framingFor([[-1.85, 51.43]], 1000, 800)?.zoom).toBe(17);
    expect(framingFor([], 1000, 800)).toBeNull();
  });
});
