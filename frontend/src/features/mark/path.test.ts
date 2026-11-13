// @vitest-environment node
import { describe, expect, it } from "vitest";
import { metaFixture } from "../../test/fixtures/meta.js";
import type { PathPoint } from "./curve.js";
import {
  addPoint,
  anchorOf,
  apiPath,
  canClose,
  closePath,
  closesAt,
  commit,
  deletePoint,
  EMPTY_PATH,
  endDirection,
  endIndex,
  HISTORY_LIMIT,
  history,
  insertAfter,
  insertAt,
  lengthM,
  movePoint,
  openPath,
  type Path,
  pathFromOutline,
  pathProblem,
  redo,
  replace,
  segmentNear,
  setKind,
  switchKind,
  undo,
} from "./path.js";

const limits = metaFixture.shapes;

const A: PathPoint = { lon: -1.855, lat: 51.428, kind: "corner" };
const B: PathPoint = { lon: -1.853, lat: 51.428, kind: "corner" };
const C: PathPoint = { lon: -1.853, lat: 51.43, kind: "smooth" };
const D: PathPoint = { lon: -1.855, lat: 51.43, kind: "corner" };

function drawn(...points: PathPoint[]): Path {
  return points.reduce((path, point) => addPoint(path, point, "end", limits), EMPTY_PATH);
}

describe("adding points", () => {
  it("adds at the end, or at the start, and never changes the path it was given", () => {
    const two = drawn(A, B);
    expect(two.points).toEqual([A, B]);
    expect(addPoint(two, C, "start", limits).points).toEqual([C, A, B]);
    expect(two.points).toEqual([A, B]);
    expect(EMPTY_PATH.points).toEqual([]);
  });

  it("adds nothing to a closed shape", () => {
    const closed = closePath(drawn(A, B, C));
    expect(addPoint(closed, D, "end", limits)).toBe(closed);
  });

  it("adds nothing on top of the point it would join, so a double tap is one point", () => {
    const one = drawn(A);
    expect(addPoint(one, { ...A, lon: A.lon + 1e-7 }, "end", limits)).toBe(one);
  });

  it("adds no more points than /meta allows", () => {
    const full = drawn(A, B);
    expect(addPoint(full, C, "end", { ...limits, path_max_points: 2 })).toBe(full);
  });

  it("names the ends, which swap with the active end", () => {
    expect(endIndex(drawn(A, B, C), "start")).toBe(0);
    expect(endIndex(drawn(A, B, C), "end")).toBe(2);
  });
});

describe("changing points", () => {
  it("moves one point", () => {
    expect(movePoint(drawn(A, B), 1, [-1.852, 51.427]).points[1]).toEqual({ lon: -1.852, lat: 51.427, kind: "corner" });
  });

  it("deletes one, and a closed shape left with two points opens into a line", () => {
    expect(deletePoint(drawn(A, B, C), 1).points).toEqual([A, C]);
    const opened = deletePoint(closePath(drawn(A, B, C)), 0);
    expect(opened).toEqual({ closed: false, points: [B, C] });
  });

  it("switches a point's kind, or sets it", () => {
    expect(switchKind(drawn(A, B), 0).points[0]?.kind).toBe("smooth");
    expect(setKind(drawn(A, B), 1, "smooth").points[1]?.kind).toBe("smooth");
    const same = drawn(A, B);
    expect(setKind(same, 0, "corner")).toBe(same);
  });

  it("inserts a point half way along the next segment, on the curve", () => {
    const straight = insertAfter(drawn(A, B), 0);
    expect(straight.points).toHaveLength(3);
    expect(straight.points[1]?.lon).toBeCloseTo(-1.854, 9);
    expect(straight.points[1]?.lat).toBeCloseTo(51.428, 9);
    expect(straight.points[1]?.kind).toBe("corner");
    // Across a closed shape's closing segment, and kept smooth beside a smooth point.
    const closed = closePath(drawn(A, B, C, D));
    expect(insertAfter(closed, 3).points).toHaveLength(5);
    expect(insertAfter(closed, 1).points[2]?.kind).toBe("smooth");
    // An open path's last point has no segment after it.
    const open = drawn(A, B);
    expect(insertAfter(open, 1)).toBe(open);
  });
});

describe("closing and opening", () => {
  it("closes an open path of three points or more", () => {
    expect(canClose(drawn(A, B))).toBe(false);
    expect(closePath(drawn(A, B)).closed).toBe(false);
    expect(canClose(drawn(A, B, C))).toBe(true);
    expect(closePath(drawn(A, B, C)).closed).toBe(true);
    expect(openPath(closePath(drawn(A, B, C)))).toEqual({ closed: false, points: [A, B, C] });
  });

  it("closes on a tap within the tolerance of the far end", () => {
    const project = ([lon, lat]: [number, number]) => ({ x: (lon + 2) * 100_000, y: (52 - lat) * 100_000 });
    const path = drawn(A, B, C);
    const first = project([A.lon, A.lat]);
    expect(closesAt(path, "end", { x: first.x + 10, y: first.y + 9 }, project)).toBe(true);
    expect(closesAt(path, "end", { x: first.x + 12, y: first.y + 12 }, project)).toBe(false);
    // Drawing from the start, the far end is the last point.
    const last = project([C.lon, C.lat]);
    expect(closesAt(path, "start", last, project)).toBe(true);
    expect(closesAt(path, "start", first, project)).toBe(false);
    // Too few points to close, or closed already.
    expect(closesAt(drawn(A, B), "end", first, project)).toBe(false);
    expect(closesAt(closePath(path), "end", first, project)).toBe(false);
  });
});

describe("undo and redo", () => {
  it("steps back and forward, and a new change drops what could be redone", () => {
    let states = history(EMPTY_PATH);
    states = commit(states, drawn(A));
    states = commit(states, drawn(A, B));
    states = undo(states);
    expect(states.present.points).toEqual([A]);
    states = redo(states);
    expect(states.present.points).toEqual([A, B]);
    states = undo(states);
    states = commit(states, drawn(A, C));
    expect(redo(states)).toBe(states);
    expect(undo(undo(undo(states))).present).toEqual(EMPTY_PATH);
  });

  it("records nothing for a change that changes nothing, and replaces without recording", () => {
    const states = commit(history(EMPTY_PATH), drawn(A));
    expect(commit(states, states.present)).toBe(states);
    const dragged = replace(states, drawn(B));
    expect(dragged.past).toBe(states.past);
    expect(undo(dragged).present).toEqual(EMPTY_PATH);
  });

  it(`keeps the last ${HISTORY_LIMIT} states`, () => {
    let states = history(EMPTY_PATH);
    for (let i = 1; i <= HISTORY_LIMIT + 20; i++) states = commit(states, drawn({ ...A, lon: A.lon + i * 1e-4 }));
    expect(states.past).toHaveLength(HISTORY_LIMIT);
  });
});

describe("the limits from /meta", () => {
  it("takes a line or shape inside them", () => {
    expect(pathProblem(drawn(A, B, C), limits)).toBeNull();
    expect(pathProblem(closePath(drawn(A, B, C)), limits)).toBeNull();
    expect(pathProblem(drawn(A), limits)).toBeNull();
  });

  it("refuses a closed shape more than the limit across, but not a line as long", () => {
    const wide = drawn(
      A,
      { lon: A.lon + 0.5, lat: A.lat, kind: "corner" },
      { lon: A.lon + 0.5, lat: A.lat + 0.1, kind: "corner" },
    );
    expect(pathProblem(wide, limits)).toBeNull();
    expect(pathProblem(closePath(wide), limits)).toMatch(/at most 25 km across/);
  });

  it("refuses a line longer than the limit", () => {
    expect(pathProblem(drawn(A, B), { ...limits, line_max_length_m: 100 })).toMatch(/at most 0\.1 km long/);
  });

  it("refuses too many points, and too many vertices", () => {
    expect(pathProblem(drawn(A, B, C), { ...limits, path_max_points: 2 })).toMatch(/at most 2 points/);
    expect(pathProblem(drawn(A, C, B), { ...limits, shape_max_vertices: 5 })).toMatch(/straight points/);
  });

  it("refuses two neighbours on top of each other, which a drag can make", () => {
    expect(pathProblem(movePoint(drawn(A, B), 1, [A.lon, A.lat]), limits)).toMatch(/on top of each other/);
  });
});

describe("lengthM", () => {
  it("measures a line along the ground, and a shape round its edge", () => {
    // 0.002 degrees of longitude at 51.428 degrees north is about 139 m.
    expect(lengthM(drawn(A, B))).toBeGreaterThan(138);
    expect(lengthM(drawn(A, B))).toBeLessThan(140);
    expect(lengthM(closePath(drawn(A, B, D)))).toBeGreaterThan(lengthM(drawn(A, B, D)));
    expect(lengthM(drawn(A))).toBe(0);
  });
});

describe("old outlines", () => {
  it("reads a line or a one-ring polygon as an all-corner path", () => {
    expect(
      pathFromOutline({
        type: "LineString",
        coordinates: [
          [-1.855, 51.428],
          [-1.853, 51.428],
        ],
      }),
    ).toEqual({
      closed: false,
      points: [A, B],
    });
    expect(
      pathFromOutline({
        type: "Polygon",
        coordinates: [
          [
            [-1.855, 51.428],
            [-1.853, 51.428],
            [-1.853, 51.43],
            [-1.855, 51.428],
          ],
        ],
      }),
    ).toEqual({ closed: true, points: [A, B, { ...C, kind: "corner" }] });
  });

  it("reads nothing from anything else", () => {
    expect(pathFromOutline({ type: "Point", coordinates: [-1.855, 51.428] })).toBeNull();
    expect(
      pathFromOutline({
        type: "MultiLineString",
        coordinates: [
          [
            [-1.855, 51.428],
            [-1.853, 51.428],
          ],
        ],
      }),
    ).toBeNull();
    const holed = [
      [-1.86, 51.42],
      [-1.84, 51.42],
      [-1.84, 51.44],
      [-1.86, 51.42],
    ];
    expect(pathFromOutline({ type: "Polygon", coordinates: [holed, holed] })).toBeNull();
    expect(pathFromOutline({ type: "LineString", coordinates: [[-1.855, 51.428]] })).toBeNull();
    expect(
      pathFromOutline({
        type: "LineString",
        coordinates: [
          ["a", 1],
          [2, 3],
        ],
      }),
    ).toBeNull();
  });
});

describe("apiPath", () => {
  it("is the path as the API takes it", () => {
    expect(apiPath(closePath(drawn(A, B, C)))).toEqual({ closed: true, points: [A, B, C] });
  });
});

describe("inserting where the line is", () => {
  const project = ([lon, lat]: [number, number]) => ({ x: (lon + 2) * 100_000, y: (52 - lat) * 100_000 });

  it("finds the segment under a tap, within reach", () => {
    const path = drawn(A, B, { ...C, kind: "corner" });
    // Half way between A and B on screen, a few pixels off the line.
    const a = project([A.lon, A.lat]);
    const b = project([B.lon, B.lat]);
    const middle = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 + 4 };
    expect(segmentNear(path, middle, project, 8)).toBe(0);
    expect(segmentNear(path, { x: middle.x, y: middle.y + 20 }, project, 8)).toBeNull();
    // Closed, the closing segment counts too.
    const c = project([C.lon, C.lat]);
    const closing = { x: (a.x + c.x) / 2, y: (a.y + c.y) / 2 };
    expect(segmentNear(path, closing, project, 8)).toBeNull();
    expect(segmentNear(closePath(path), closing, project, 8)).toBe(2);
  });

  it("inserts a point at a place, after a segment's start", () => {
    const inserted = insertAt(drawn(A, B), 0, [-1.854, 51.4281]);
    expect(inserted.points).toEqual([A, { lon: -1.854, lat: 51.4281, kind: "corner" }, B]);
  });
});

describe("anchorOf", () => {
  it("is the spot itself, a line's half way point, and somewhere inside a shape", () => {
    expect(anchorOf(EMPTY_PATH)).toBeNull();
    expect(anchorOf(drawn(A))).toEqual([A.lon, A.lat]);
    const half = anchorOf(drawn(A, B));
    expect(half?.[0]).toBeCloseTo(-1.854, 6);
    expect(half?.[1]).toBeCloseTo(51.428, 6);
    const inside = anchorOf(closePath(drawn(A, B, { ...C, kind: "corner" }, D)));
    expect(inside?.[0]).toBeCloseTo(-1.854, 6);
    expect(inside?.[1]).toBeCloseTo(51.429, 6);
  });
});

describe("endDirection", () => {
  it("names the active end by the compass, from the other end", () => {
    expect(endDirection(drawn(A, B), "end")).toBe("east");
    expect(endDirection(drawn(A, B), "start")).toBe("west");
    expect(endDirection(drawn(B, C), "end")).toBe("north");
    expect(endDirection(drawn(A, C), "end")).toBe("north-east");
    expect(endDirection(drawn(A), "end")).toBeNull();
    expect(endDirection(closePath(drawn(A, B, C)), "end")).toBeNull();
  });
});
