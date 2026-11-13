// @vitest-environment node
import { describe, expect, it } from "vitest";
import vectorsText from "../../../../docs/architecture/curve-vectors.json?raw";
import { CURVE, type CurvePath, derive, segmentVertexCounts } from "./curve.js";

interface Vector {
  name: string;
  path: CurvePath;
  expected: { type: "LineString" | "Polygon"; coordinates: unknown };
  extends?: string;
  unchanged?: { base: [number, number]; extended: [number, number] };
}

const shared = JSON.parse(vectorsText) as { curve: string; tolerance_deg: number; vectors: Vector[] };
// A tie in the seventh place can round either way in either language, which is one step of the tolerance.
const TOLERANCE = shared.tolerance_deg * (1 + 1e-9);

function vertices(geometry: ReturnType<typeof derive>): number[][] {
  return geometry.type === "Polygon" ? (geometry.coordinates[0] ?? []) : geometry.coordinates;
}

function expectedVertices(vector: Vector): number[][] {
  const { type, coordinates } = vector.expected;
  return (type === "Polygon" ? (coordinates as number[][][])[0] : (coordinates as number[][])) ?? [];
}

function expectClose(actual: number[][], expected: number[][], name: string): void {
  expect(actual.length, `${name}: vertex count`).toBe(expected.length);
  actual.forEach((vertex, index) => {
    const want = expected[index] ?? [];
    for (const axis of [0, 1]) {
      const difference = Math.abs((vertex[axis] ?? Number.NaN) - (want[axis] ?? Number.NaN));
      expect(difference, `${name}: vertex ${index}, axis ${axis}`).toBeLessThanOrEqual(TOLERANCE);
    }
  });
}

describe("the curve", () => {
  it("is the curve the shared vectors describe", () => {
    expect(shared.curve).toBe(CURVE);
    expect(shared.vectors.length).toBeGreaterThanOrEqual(12);
  });

  for (const vector of shared.vectors) {
    it(`derives "${vector.name}" as the server does`, () => {
      const geometry = derive(vector.path);
      expect(geometry.type).toBe(vector.expected.type);
      expectClose(vertices(geometry), expectedVertices(vector), vector.name);
      // The vertex count the limits are checked by agrees with what is drawn.
      const counted = segmentVertexCounts(vector.path).reduce((sum, count) => sum + count, 1);
      expect(counted).toBe(vertices(geometry).length);
    });
  }

  for (const vector of shared.vectors.filter((each) => each.extends !== undefined)) {
    it(`leaves every segment more than one from the new point alone in "${vector.name}"`, () => {
      const base = shared.vectors.find((each) => each.name === vector.extends);
      const unchanged = vector.unchanged;
      if (!base || !unchanged) throw new Error(`${vector.name} names a base or slice that isn't there`);
      const before = vertices(derive(base.path)).slice(...unchanged.base);
      const after = vertices(derive(vector.path)).slice(...unchanged.extended);
      expect(before.length).toBeGreaterThan(0);
      expect(after).toEqual(before);
    });
  }

  it("closes a ring back on its first point", () => {
    const vector = shared.vectors.find((each) => each.path.closed);
    if (!vector) throw new Error("No closed vector");
    const ring = vertices(derive(vector.path));
    expect(ring.at(-1)).toEqual(ring[0]);
  });

  it("refuses a path too short to draw", () => {
    expect(() => derive({ closed: false, points: [{ lon: -1.85, lat: 51.4, kind: "corner" }] })).toThrow(RangeError);
    expect(() =>
      derive({
        closed: true,
        points: [
          { lon: -1.85, lat: 51.4, kind: "corner" },
          { lon: -1.84, lat: 51.4, kind: "corner" },
        ],
      }),
    ).toThrow(RangeError);
  });
});
