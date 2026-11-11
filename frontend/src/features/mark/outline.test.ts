// @vitest-environment node
import { describe, expect, it } from "vitest";
import {
  addPoint,
  canClose,
  canFinishLine,
  closeShape,
  distanceToOutline,
  finishLine,
  type LngLat,
  NEW_OUTLINE,
  type Outline,
  outlineGeometry,
  outlineProblem,
  undoPoint,
} from "./outline.js";

const A: LngLat = [-1.855, 51.428];
const B: LngLat = [-1.853, 51.428];
const C: LngLat = [-1.853, 51.43];

function drawn(...points: LngLat[]): Outline {
  return points.reduce(addPoint, NEW_OUTLINE);
}

describe("the outline tool", () => {
  it("adds corners and takes the last one back", () => {
    const outline = drawn(A, B, C);
    expect(outline.points).toEqual([A, B, C]);
    expect(undoPoint(outline).points).toEqual([A, B]);
    expect(NEW_OUTLINE.points).toEqual([]);
  });

  it("closes a shape only with three corners, and finishes a line with two", () => {
    expect(canClose(drawn(A, B))).toBe(false);
    expect(canFinishLine(drawn(A, B))).toBe(true);
    expect(closeShape(drawn(A, B)).shape).toBe("drawing");
    expect(closeShape(drawn(A, B, C)).shape).toBe("polygon");
    expect(finishLine(drawn(A, B)).shape).toBe("line");
  });

  it("adds nothing to a finished shape, and undoing opens it again", () => {
    const closed = closeShape(drawn(A, B, C));
    expect(addPoint(closed, [0, 0])).toBe(closed);
    expect(undoPoint(closed)).toEqual({ points: [A, B, C], shape: "drawing" });
  });
});

describe("outlineGeometry", () => {
  it("closes the ring of a polygon", () => {
    expect(outlineGeometry(closeShape(drawn(A, B, C)))).toEqual({ type: "Polygon", coordinates: [[A, B, C, A]] });
  });

  it("sends a line as a line", () => {
    expect(outlineGeometry(finishLine(drawn(A, B)))).toEqual({ type: "LineString", coordinates: [A, B] });
  });

  it("keeps the work of an outline saved part-way", () => {
    expect(outlineGeometry(drawn(A, B, C))?.type).toBe("Polygon");
    expect(outlineGeometry(drawn(A, B))?.type).toBe("LineString");
    expect(outlineGeometry(drawn(A))).toBeNull();
    expect(outlineGeometry(null)).toBeNull();
  });
});

describe("outlineProblem", () => {
  it("takes a point inside a closed shape, however far from its corners", () => {
    const big: Outline = closeShape(drawn([-1.87, 51.42], [-1.84, 51.42], [-1.84, 51.44], [-1.87, 51.44]));
    expect(distanceToOutline(big, [-1.855, 51.43])).toBe(0);
    expect(outlineProblem(big, [-1.855, 51.43])).toBeNull();
  });

  it("measures to the nearest edge of a line", () => {
    expect(distanceToOutline(finishLine(drawn(A, B)), [-1.854, 51.429])).toBeCloseTo(0.001, 6);
  });

  it("refuses an outline drawn away from the mark, or one too big", () => {
    expect(outlineProblem(drawn(A, B, C), [-1.7, 51.43])).toMatch(/round your mark/);
    expect(outlineProblem(drawn(A, [-1.75, 51.428]), A)).toMatch(/too big/);
    expect(outlineProblem(null, A)).toBeNull();
  });
});
