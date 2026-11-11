// @vitest-environment node
import { describe, expect, it } from "vitest";
import { centreFor } from "./mapView.js";

const POINT: [number, number] = [-1.8542, 51.4286];

/** Where `point` lands on screen, from the centre, with the map centred on `centre`. */
function screenOffset(point: [number, number], centre: [number, number], zoom: number, bearing: number) {
  const cos = Math.cos((point[1] * Math.PI) / 180);
  const metresPerPx = (40_075_016.686 * cos) / (512 * 2 ** zoom);
  const east = ((point[0] - centre[0]) * 111_320 * cos) / metresPerPx;
  const south = (-(point[1] - centre[1]) * 111_320) / metresPerPx;
  const angle = (bearing * Math.PI) / 180;
  // With bearing b, the top of the screen faces b degrees clockwise from north.
  return { x: east * Math.cos(angle) + south * Math.sin(angle), y: -east * Math.sin(angle) + south * Math.cos(angle) };
}

describe("centreFor", () => {
  it("centres on the point when nothing covers the map", () => {
    expect(centreFor(POINT, 16, 0, { x: 0, y: 0 })).toEqual(POINT);
  });

  it("moves the centre so the point lands in the middle of what is uncovered", () => {
    for (const bearing of [0, 30, -110]) {
      const offset = { x: -200, y: -150 };
      const centre = centreFor(POINT, 16, bearing, offset);
      const landed = screenOffset(POINT, centre, 16, bearing);
      expect(landed.x).toBeCloseTo(offset.x, 3);
      expect(landed.y).toBeCloseTo(offset.y, 3);
    }
  });

  it("knows that with the map turned to face east, east is up the screen", () => {
    const centre: [number, number] = [POINT[0] - 0.001, POINT[1]];
    const landed = screenOffset(POINT, centre, 16, 90);
    expect(landed.x).toBeCloseTo(0, 6);
    expect(landed.y).toBeLessThan(0);
  });

  it("puts the centre east of a point that is to sit left of it", () => {
    const [lng] = centreFor(POINT, 16, 0, { x: -200, y: 0 });
    expect(lng).toBeGreaterThan(POINT[0]);
  });
});
