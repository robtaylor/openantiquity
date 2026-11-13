// @vitest-environment node
import { describe, expect, it } from "vitest";
import { metaFixture } from "../../test/fixtures/meta.js";
import { DOT_CLEARANCE_PX, dotsInView } from "./MidpointDots.js";
import { closePath, type LngLat, type Path, segmentMiddles } from "./path.js";

const limits = metaFixture.shapes;
const SIZE = { width: 1000, height: 800 };
/** One pixel a metre-ish: a hundred-thousandth of a degree a pixel, flat. */
const project = ([lon, lat]: LngLat) => ({ x: (lon + 2) * 100_000, y: (52 - lat) * 100_000 });

/** A path of straight points at these screen places. */
function onScreen(...places: Array<[number, number]>): Path {
  return {
    closed: false,
    points: places.map(([x, y]) => ({ lon: x / 100_000 - 2, lat: 52 - y / 100_000, kind: "corner" })),
  };
}

function all(path: Path): number[] {
  return path.points.map((_, index) => index);
}

describe("which midpoint dots are shown", () => {
  it("puts one half way along each segment long enough to keep its target off the points' targets", () => {
    const path = onScreen([100, 100], [300, 100], [300, 160]);
    const dots = dotsInView(path, project, SIZE, all(path), false, limits);
    expect(dots.map((dot) => dot.index)).toEqual([0]);
    expect(dots[0]?.x).toBeCloseTo(200, 6);
    expect(dots[0]?.y).toBeCloseTo(100, 6);
    // 60 px apart leaves 30 px from each end: under the 38 px that keeps a 32 px target off a 44 px one.
    expect(DOT_CLEARANCE_PX).toBe(38);
    const longer = onScreen([100, 100], [300, 100], [300, 180]);
    expect(dotsInView(longer, project, SIZE, all(longer), false, limits).map((dot) => dot.index)).toEqual([0, 1]);
  });

  it("gives way to any other point's handle too, where the line loops back past it", () => {
    const path = onScreen([100, 100], [300, 100], [300, 300], [200, 110]);
    const shown = dotsInView(path, project, SIZE, all(path), false, limits).map((dot) => dot.index);
    // The first segment's middle, (200, 100), is 10 px from the fourth point.
    expect(shown).not.toContain(0);
    expect(shown).toContain(1);
  });

  it("counts a closed shape's closing segment", () => {
    const path = closePath(onScreen([100, 100], [300, 100], [300, 300]));
    expect(dotsInView(path, project, SIZE, all(path), false, limits).map((dot) => dot.index)).toEqual([0, 1, 2]);
  });

  it("shows only what is in view", () => {
    const path = onScreen([100, 100], [300, 100], [2400, 100]);
    expect(dotsInView(path, project, SIZE, [0, 1], false, limits).map((dot) => dot.index)).toEqual([0]);
  });

  it("projects no middle that lies outside the padded bounds of the view", () => {
    const path = onScreen([100, 100], [300, 100], [2400, 100], [2600, 100]);
    const projected: LngLat[] = [];
    const counting = (point: LngLat) => {
      projected.push(point);
      return project(point);
    };
    // The bounds reach as far as x 1200 on this projection, so the last two middles are left out unprojected.
    const bounds = { west: -2, east: 1200 / 100_000 - 2, south: 51, north: 52 };
    const dots = dotsInView(path, counting, SIZE, [0, 1], false, limits, bounds);
    expect(dots.map((dot) => dot.index)).toEqual([0]);
    const middles = segmentMiddles(path);
    expect(projected).toContain(middles[0]);
    expect(projected).not.toContain(middles[1]);
    expect(projected).not.toContain(middles[2]);
  });

  it("shows none while the handles are thinned, for a spot, or at the point limit", () => {
    const path = onScreen([100, 100], [300, 100]);
    expect(dotsInView(path, project, SIZE, all(path), true, limits)).toEqual([]);
    expect(dotsInView(onScreen([100, 100]), project, SIZE, [0], false, limits)).toEqual([]);
    expect(dotsInView(path, project, SIZE, all(path), false, { ...limits, path_max_points: 2 })).toEqual([]);
    expect(dotsInView(path, project, SIZE, all(path), false, undefined)).toEqual([]);
  });
});
