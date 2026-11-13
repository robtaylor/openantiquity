// @vitest-environment node
import { describe, expect, it } from "vitest";
import { centreFor, clearOf } from "./mapView.js";

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

describe("clearOf", () => {
  const phoneStage = { left: 0, top: 0, right: 390, bottom: 400 };

  it("is the whole stage when nothing floats on it", () => {
    expect(clearOf(phoneStage, [])).toEqual(phoneStage);
  });

  it("takes a full-width search box off the top and the map's buttons off the right", () => {
    const search = { left: 12, top: 12, right: 378, bottom: 56 };
    const buttons = { left: 334, top: 64, right: 378, bottom: 260 };
    expect(clearOf(phoneStage, [search, buttons])).toEqual({ left: 0, top: 56, right: 334, bottom: 400 });
  });

  it("takes a drawing bar off the bottom", () => {
    const bar = { left: 8, top: 300, right: 382, bottom: 390 };
    expect(clearOf(phoneStage, [bar])).toEqual({ left: 0, top: 0, right: 390, bottom: 300 });
  });

  it("takes a short search box off the top on a wide stage, not off the left", () => {
    const stage = { left: 56, top: 0, right: 1040, bottom: 870 };
    const search = { left: 68, top: 12, right: 428, bottom: 56 };
    expect(clearOf(stage, [search])).toEqual({ left: 56, top: 56, right: 1040, bottom: 870 });
  });

  it("passes over boxes that are empty or off the stage", () => {
    const empty = { left: 20, top: 20, right: 20, bottom: 20 };
    const away = { left: 500, top: 0, right: 600, bottom: 50 };
    expect(clearOf(phoneStage, [empty, away])).toEqual(phoneStage);
  });
});

/** A box whose edges are getters on its prototype, as a DOMRect's are. */
class Rect {
  constructor(
    private readonly x: number,
    private readonly y: number,
    private readonly w: number,
    private readonly h: number,
  ) {}
  get left(): number {
    return this.x;
  }
  get top(): number {
    return this.y;
  }
  get right(): number {
    return this.x + this.w;
  }
  get bottom(): number {
    return this.y + this.h;
  }
}

describe("clearOf on the page's own boxes", () => {
  it("reads edges that are getters, as a DOMRect's are", () => {
    const stage = new Rect(0, 0, 390, 400);
    const search = new Rect(12, 12, 366, 44);
    expect(clearOf(stage, [search])).toEqual({ left: 0, top: 56, right: 390, bottom: 400 });
  });
});
