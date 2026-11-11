import { describe, expect, it } from "vitest";
import { BORDER_COVERAGE, BORDER_VIEW, ENGLAND_SPOT, WALES_SPOT } from "../../../test/fixtures/coverage.js";
import { CoverageError, capturesIn, coverageBox, gapsIn, insideRing, MAX_CELLS, parseCoverage } from "./coverage.js";

const tiles = parseCoverage(BORDER_COVERAGE);

describe("parseCoverage", () => {
  it("reads each tile's square, name and capture", () => {
    expect(tiles).toHaveLength(9);
    const first = tiles[0];
    expect(first?.tile).toBe("SO50se");
    expect(first?.capture).toBe("2022 composite");
    expect(first?.resolutionM).toBe(1);
    expect(first?.ring).toHaveLength(5);
    expect(first?.bounds[0]).toBeLessThan(first?.bounds[2] ?? 0);
  });

  it("refuses anything that isn't polygons in a collection", () => {
    expect(() => parseCoverage({ features: [] })).toThrow(CoverageError);
    expect(() =>
      parseCoverage({ type: "FeatureCollection", features: [{ type: "Feature", geometry: { type: "Point" } }] }),
    ).toThrow(CoverageError);
  });

  it("leaves out a capture the API doesn't give", () => {
    const [tile] = parseCoverage({
      type: "FeatureCollection",
      features: [{ ...BORDER_COVERAGE.features[0], properties: { tile: "SO50se" } }],
    });
    expect(tile?.capture).toBeNull();
    expect(tile?.resolutionM).toBeNull();
  });
});

describe("insideRing", () => {
  it("tells England from Wales at the border", () => {
    const at = (spot: { lng: number; lat: number }) =>
      tiles.some((tile) => insideRing([spot.lng, spot.lat], tile.ring));
    expect(at(ENGLAND_SPOT)).toBe(true);
    expect(at(WALES_SPOT)).toBe(false);
  });
});

describe("coverageBox", () => {
  it("pushes a view out to a quarter-degree grid, so small moves ask the same question", () => {
    expect(coverageBox([-1.86, 51.42, -1.84, 51.44])).toEqual([-2, 51.25, -1.75, 51.5]);
    expect(coverageBox([-1.87, 51.41, -1.83, 51.45])).toEqual([-2, 51.25, -1.75, 51.5]);
  });
});

describe("capturesIn", () => {
  it("names each capture once", () => {
    expect(capturesIn(tiles, BORDER_VIEW)).toEqual(["2022 composite"]);
    expect(capturesIn(tiles, [0, 0, 1, 1])).toEqual([]);
  });
});

describe("gapsIn", () => {
  it("shades the squares on the Welsh side and leaves the English ones", () => {
    const gaps = gapsIn(BORDER_VIEW, tiles);
    if (!gaps) throw new Error("expected gaps");
    expect(gaps.rings.length).toBeGreaterThan(0);
    expect(gaps.rings.length).toBeLessThan(gaps.cells);
    const inGap = (spot: { lng: number; lat: number }) =>
      gaps.rings.some((ring) => insideRing([spot.lng, spot.lat], ring));
    expect(inGap(WALES_SPOT)).toBe(true);
    expect(inGap(ENGLAND_SPOT)).toBe(false);
  });

  it("shades every square where there is no coverage at all", () => {
    const gaps = gapsIn(BORDER_VIEW, []);
    expect(gaps?.rings.length).toBe(gaps?.cells);
  });

  it("gives up on a view too wide to shade square by square", () => {
    expect(gapsIn([-6, 50, 2, 56], tiles)).toBeNull();
    expect(MAX_CELLS).toBeGreaterThan(100);
  });
});
