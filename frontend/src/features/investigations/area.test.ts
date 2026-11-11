import { describe, expect, it } from "vitest";
import { areaShape, bboxParam, boundsOf, polygonOf } from "./area.js";

describe("areaShape", () => {
  it("reads a polygon and a multipolygon's rings", () => {
    const polygon = polygonOf([-1.9, 51.4, -1.8, 51.5]);
    expect(areaShape(polygon)?.rings).toHaveLength(1);
    const multi = { type: "MultiPolygon" as const, coordinates: [polygon.coordinates, polygon.coordinates] };
    expect(areaShape(multi)?.rings).toHaveLength(2);
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
