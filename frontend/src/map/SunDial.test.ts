// @vitest-environment node
import { describe, expect, it } from "vitest";
import { bearingFromCentre, dialPoint } from "./SunDial.js";

const RECT = { left: 100, top: 200, width: 96, height: 96 };

describe("bearingFromCentre", () => {
  it("reads compass bearings off a box", () => {
    expect(bearingFromCentre(RECT, 148, 200)).toBeCloseTo(0, 5);
    expect(bearingFromCentre(RECT, 196, 248)).toBeCloseTo(90, 5);
    expect(bearingFromCentre(RECT, 148, 296)).toBeCloseTo(180, 5);
    expect(bearingFromCentre(RECT, 100, 248)).toBeCloseTo(270, 5);
    expect(bearingFromCentre(RECT, 100, 200)).toBeCloseTo(315, 5);
  });
});

describe("dialPoint", () => {
  it("puts compass bearings round the dial, north at the top, when the map is north-up", () => {
    expect(dialPoint(0, 0, 30)).toEqual({ x: 50, y: 20 });
    const east = dialPoint(90, 0, 30);
    expect(east.x).toBeCloseTo(80, 9);
    expect(east.y).toBeCloseTo(50, 9);
    const south = dialPoint(180, 0, 30);
    expect(south.x).toBeCloseTo(50, 9);
    expect(south.y).toBeCloseTo(80, 9);
  });

  it("turns with the map, so each point is drawn where that direction is on screen", () => {
    // With east at the top of the screen, north is to the left and east straight up.
    const north = dialPoint(0, 90, 30);
    expect(north.x).toBeCloseTo(20, 9);
    expect(north.y).toBeCloseTo(50, 9);
    const east = dialPoint(90, 90, 30);
    expect(east.x).toBeCloseTo(50, 9);
    expect(east.y).toBeCloseTo(20, 9);
    // A map turned 46 degrees anticlockwise, as a two-finger twist leaves it.
    const tilted = dialPoint(0, -46.2, 30);
    expect(tilted.x).toBeGreaterThan(50);
    expect(tilted.y).toBeLessThan(50);
  });
});
