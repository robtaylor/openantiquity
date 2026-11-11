import { describe, expect, it } from "vitest";
import { areaShape, bboxParam, boundsOf, polygonOf } from "./area.js";
import { areaFeatures } from "./useAreaOnMap.js";

/** A four-degree square with a hole in the middle. */
const HOLED = {
  type: "Polygon" as const,
  coordinates: [
    [
      [0, 0],
      [4, 0],
      [4, 4],
      [0, 4],
      [0, 0],
    ],
    [
      [1, 1],
      [1, 3],
      [3, 3],
      [3, 1],
      [1, 1],
    ],
  ],
};

describe("areaShape", () => {
  it("reads a polygon and a multipolygon's polygons", () => {
    const polygon = polygonOf([-1.9, 51.4, -1.8, 51.5]);
    expect(areaShape(polygon)?.polygons).toHaveLength(1);
    const multi = { type: "MultiPolygon" as const, coordinates: [polygon.coordinates, polygon.coordinates] };
    expect(areaShape(multi)?.polygons).toHaveLength(2);
  });

  it("keeps a hole with the polygon it is cut from", () => {
    const shape = areaShape(HOLED);
    expect(shape?.polygons).toHaveLength(1);
    expect(shape?.polygons[0]).toHaveLength(2);
    expect(shape && boundsOf(shape)).toEqual([0, 0, 4, 4]);
  });

  it("draws nothing for no area, a point, or broken coordinates", () => {
    expect(areaShape(null)).toBeNull();
    expect(areaShape({ type: "Point", coordinates: [0, 0] })).toBeNull();
    expect(
      areaShape({
        type: "Polygon",
        coordinates: [
          [
            [0, 0],
            [1, "x"],
            [1, 1],
            [0, 0],
          ],
        ],
      }),
    ).toBeNull();
    expect(
      areaShape({
        type: "Polygon",
        coordinates: [
          [
            [0, 0],
            [1, 1],
          ],
        ],
      }),
    ).toBeNull();
  });
});

describe("boundsOf and polygonOf", () => {
  it("go round a box and back", () => {
    const bounds: [number, number, number, number] = [-1.91234567, 51.4, -1.8, 51.5];
    const shape = areaShape(polygonOf(bounds));
    expect(shape && boundsOf(shape)).toEqual([-1.91235, 51.4, -1.8, 51.5]);
  });
});

describe("bboxParam", () => {
  it("rounds outwards to about a hundred metres", () => {
    expect(bboxParam([-1.91234, 51.40011, -1.80001, 51.49999])).toBe("-1.913,51.400,-1.800,51.500");
  });
});

describe("areaFeatures", () => {
  it("draws a polygon with a hole as one feature that keeps the hole", () => {
    const features = areaFeatures(areaShape(HOLED)).features;
    expect(features).toHaveLength(1);
    expect(features[0]?.geometry).toEqual(HOLED);
  });

  it("draws each polygon of a multipolygon as a feature of its own", () => {
    const multi = {
      type: "MultiPolygon" as const,
      coordinates: [HOLED.coordinates, polygonOf([5, 5, 6, 6]).coordinates],
    };
    expect(areaFeatures(areaShape(multi)).features).toHaveLength(2);
  });
});
