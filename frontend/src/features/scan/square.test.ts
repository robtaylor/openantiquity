import { describe, expect, it } from "vitest";
import { coverageLayers } from "../../map/overlayLayers.js";
import { visibleCentre } from "../../map/visibleArea.js";
import { coverageOf, SQUARE_SPOT, squareAt, squareEastOf } from "../../test/fixtures/squares.js";
import {
  areaKm2,
  coverageBox,
  coverageFeatures,
  frameSquare,
  inSquare,
  keepMiddle,
  SQUARE_FILL,
  squareFeatures,
} from "./square.js";

const SQUARE = squareAt(...SQUARE_SPOT);

/** Pixels across a box at a zoom, as MapLibre draws 512 px a tile. */
function pixels(bbox: readonly number[], zoom: number): { across: number; up: number } {
  const [west, south, east, north] = bbox as [number, number, number, number];
  const lat = ((south + north) / 2) * (Math.PI / 180);
  const world = 512 * 2 ** zoom;
  return { across: ((east - west) / 360) * world, up: ((north - south) / 360) * world * (1 / Math.cos(lat)) };
}

describe("framing a square", () => {
  it("fills most of the uncovered map across its narrower side, centred in it", () => {
    const cover = { left: 56, right: 400, top: 0, bottom: 28 };
    const frame = frameSquare(SQUARE.bbox, 1440, 900, cover);
    const size = pixels(SQUARE.bbox, frame.zoom);
    const visible = { width: 1440 - 456, height: 900 - 28 };
    // The height is the narrower side here: the square fills that much of it, and fits across.
    expect(size.up).toBeCloseTo(visible.height * SQUARE_FILL, 0);
    expect(size.across).toBeLessThanOrEqual(visible.width * SQUARE_FILL + 0.5);
    // The camera points east of the square's middle, so the middle falls in the middle of the part the panel leaves.
    expect(frame.lng).toBeGreaterThan((SQUARE.bbox[0] + SQUARE.bbox[2]) / 2);
  });

  it("fits a phone's narrow uncovered strip, above the sheet", () => {
    const frame = frameSquare(SQUARE.bbox, 390, 844, { left: 0, right: 0, top: 68, bottom: 400 });
    const size = pixels(SQUARE.bbox, frame.zoom);
    expect(size.across).toBeLessThanOrEqual(390 * SQUARE_FILL + 0.5);
    expect(size.up).toBeLessThanOrEqual((844 - 468) * SQUARE_FILL + 0.5);
    // The middle of the square is above the middle of the window, where the sheet leaves the map in sight.
    expect(frame.lat).toBeLessThan((SQUARE.bbox[1] + SQUARE.bbox[3]) / 2);
  });

  it("refuses a box that doesn't run west to east", () => {
    expect(() => frameSquare([1, 0, 0, 1], 100, 100)).toThrow(/west to east/);
  });
});

describe("the square on the map", () => {
  it("outlines the square and shades the world with the square cut out, the hole wound against the outside", () => {
    const { outline, shade } = squareFeatures(SQUARE);
    expect(outline.features).toHaveLength(1);
    const polygon = shade.features[0]?.geometry;
    if (polygon?.type !== "Polygon") throw new Error("The shade must be a polygon");
    const [outer, hole] = polygon.coordinates;
    const area = (ring: Array<[number, number]> | undefined) =>
      (ring ?? []).reduce((sum, [x1, y1], i, all) => {
        const [x2, y2] = all[(i + 1) % all.length] as [number, number];
        return sum + x1 * y2 - x2 * y1;
      }, 0);
    expect(area(outer)).toBeGreaterThan(0);
    expect(area(hole)).toBeLessThan(0);
  });

  it("draws nothing without a square", () => {
    expect(squareFeatures(null).outline.features).toEqual([]);
    expect(squareFeatures(null).shade.features).toEqual([]);
  });

  it("tells a point in the square from one in the next", () => {
    expect(inSquare(SQUARE.square, SQUARE.centre)).toBe(true);
    expect(inSquare(SQUARE.square, squareEastOf(1).centre)).toBe(false);
  });
});

describe("the coverage box", () => {
  it("pushes the view out to a grid, so small moves ask for the same box", () => {
    const a = coverageBox([-1.9, 51.4, -1.8, 51.45]);
    const b = coverageBox([-1.899, 51.401, -1.801, 51.449]);
    expect(a).toEqual(b);
    expect(a).toEqual([-1.9, 51.4, -1.8, 51.46]);
  });

  it("asks nothing for a view wider than the server answers for", () => {
    // About 70 km by 45 km: a desktop screen at zoom 10.
    expect(areaKm2([-2.4, 51.2, -1.4, 51.6])).toBeGreaterThan(2500);
    expect(coverageBox([-2.4, 51.2, -1.4, 51.6])).toBeNull();
  });

  it("turns the server's squares into features carrying their counts", () => {
    const features = coverageFeatures(coverageOf([{ square: SQUARE, scans: 3, marked: 1 }]));
    expect(features.features).toEqual([
      expect.objectContaining({ id: SQUARE.square, properties: { square: SQUARE.square, scans: 3 } }),
    ]);
  });
});

describe("the coverage layer's look", () => {
  it("shades by `scans`, and writes the count from zoom 12 only where the map has glyphs", () => {
    const withGlyphs = coverageLayers("overlay-coverage", true);
    expect(JSON.stringify(withGlyphs[0]?.opacity)).toContain("scans");
    const count = withGlyphs.find((entry) => entry.layer.id === "coverage-count")?.layer;
    expect(count).toMatchObject({ type: "symbol", minzoom: 12 });
    expect(coverageLayers("overlay-coverage").map((entry) => entry.layer.id)).toEqual([
      "coverage-fill",
      "coverage-line",
    ]);
  });
});

describe("keeping the middle of the map when the sheet moves", () => {
  const camera = { lng: -1.85, lat: 51.43, zoom: 14.5, bearing: 0 };
  const half = { left: 0, right: 0, top: 68, bottom: 470 };
  const peek = { left: 0, right: 0, top: 68, bottom: 200 };

  it("points the camera so the ground in the middle of what showed is in the middle of what shows now", () => {
    const before = visibleCentre(camera, half);
    const moved = keepMiddle(camera, half, peek);
    if (!moved) throw new Error("A north-up map should be moved");
    const after = visibleCentre({ ...camera, ...moved }, peek);
    expect(after.lng).toBeCloseTo(before.lng, 9);
    expect(after.lat).toBeCloseTo(before.lat, 9);
    // A shorter sheet leaves more map below, so the camera goes north to keep the middle where it was.
    expect(moved.lat).toBeGreaterThan(camera.lat);
  });

  it("leaves the map be when nothing moved, or when it is turned from north", () => {
    expect(keepMiddle(camera, half, half)).toBeNull();
    expect(keepMiddle({ ...camera, bearing: 30 }, half, peek)).toBeNull();
  });
});
