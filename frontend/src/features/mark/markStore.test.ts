import { beforeEach, describe, expect, it } from "vitest";
import { metaFixture } from "../../test/fixtures/meta.js";
import { hasUnkeptLine, type MarkFields, useMarkStore } from "./markStore.js";
import { HISTORY_LIMIT, type Path } from "./path.js";

/**
 * "Change the shape" calls a change unsaved while undo has somewhere to go
 * (`shape.past`), and the store calls a path unkept while it isn't the path
 * last kept (`kept`, which `hasUnkeptLine` reads). These say where the two
 * agree and where they part.
 */

const LINE: Path = {
  closed: false,
  points: [
    { lon: -1.85, lat: 51.4, kind: "corner" },
    { lon: -1.84, lat: 51.41, kind: "corner" },
    { lon: -1.83, lat: 51.4, kind: "corner" },
  ],
};

function undoHasSomewhereToGo(state: MarkFields): boolean {
  return state.shape.past.length > 0;
}

function notAsKept(state: MarkFields): boolean {
  return state.shape.present !== state.kept;
}

function both(): [boolean, boolean, boolean] {
  const state = useMarkStore.getState();
  return [undoHasSomewhereToGo(state), notAsKept(state), hasUnkeptLine(state)];
}

beforeEach(() => {
  useMarkStore.getState().edit("finding:test:1", LINE);
});

describe("two ways of saying a taken-up path has changed", () => {
  it("agree on the path as it was taken up", () => {
    expect(both()).toEqual([false, false, false]);
  });

  it("agree after a change, its undo and its redo", () => {
    const mark = useMarkStore.getState();
    mark.switchPointKind(1);
    expect(both()).toEqual([true, true, true]);
    mark.undo();
    expect(both()).toEqual([false, false, false]);
    mark.redo();
    expect(both()).toEqual([true, true, true]);
  });

  it("agree after two changes and one undo", () => {
    const mark = useMarkStore.getState();
    mark.switchPointKind(1);
    mark.switchPointKind(2);
    mark.undo();
    expect(both()).toEqual([true, true, true]);
    mark.undo();
    expect(both()).toEqual([false, false, false]);
  });

  it("agree when a change is undone by hand rather than by undo: both still call it changed", () => {
    const mark = useMarkStore.getState();
    mark.switchPointKind(1);
    mark.switchPointKind(1);
    expect(useMarkStore.getState().shape.present.points).toEqual(LINE.points);
    expect(both()).toEqual([true, true, true]);
  });

  it("part once more changes are made than undo keeps, and all of them are undone", () => {
    const mark = useMarkStore.getState();
    for (let i = 0; i <= HISTORY_LIMIT; i++) mark.switchPointKind(1);
    for (let i = 0; i < HISTORY_LIMIT; i++) mark.undo();
    // Undo has nowhere left to go, but the path is one change away from the one taken up.
    expect(both()).toEqual([false, true, true]);
  });
});

/**
 * The first tap places a point before its finder has said which kind they
 * want, and its kind shows only once a shape closes on it. So while it is
 * the only point, it follows the kind chosen for the next one.
 */
describe("the first point and the kind chosen for the next", () => {
  const LIMITS = metaFixture.shapes;

  function kinds(): string[] {
    return useMarkStore.getState().shape.present.points.map((point) => point.kind);
  }

  beforeEach(() => {
    useMarkStore.getState().start();
  });

  it("follows the choice while it is the only point, so a curved shape closes smoothly", () => {
    const mark = useMarkStore.getState();
    mark.add([-1.85, 51.4], LIMITS);
    expect(kinds()).toEqual(["corner"]);

    mark.setNextKind("smooth");
    expect(kinds()).toEqual(["smooth"]);
    mark.add([-1.84, 51.41], LIMITS);
    mark.add([-1.83, 51.4], LIMITS);
    mark.closeShape();
    expect(kinds()).toEqual(["smooth", "smooth", "smooth"]);
    expect(useMarkStore.getState().shape.present.closed).toBe(true);
  });

  it("follows the choice back again", () => {
    const mark = useMarkStore.getState();
    mark.setNextKind("smooth");
    mark.add([-1.85, 51.4], LIMITS);
    expect(kinds()).toEqual(["smooth"]);
    mark.setNextKind("corner");
    expect(kinds()).toEqual(["corner"]);
  });

  it("leaves the points alone once there are two", () => {
    const mark = useMarkStore.getState();
    mark.add([-1.85, 51.4], LIMITS);
    mark.add([-1.84, 51.41], LIMITS);
    mark.setNextKind("smooth");
    expect(kinds()).toEqual(["corner", "corner"]);
    expect(useMarkStore.getState().nextKind).toBe("smooth");
  });

  it("gives undo nothing more to step through", () => {
    const mark = useMarkStore.getState();
    mark.add([-1.85, 51.4], LIMITS);
    const steps = useMarkStore.getState().shape.past.length;
    mark.setNextKind("smooth");
    expect(useMarkStore.getState().shape.past.length).toBe(steps);
    mark.undo();
    expect(kinds()).toEqual([]);
  });

  it("doesn't count as a change to a saved spot taken up to draw from", () => {
    const spot: Path = { closed: false, points: [{ lon: -1.85, lat: 51.4, kind: "corner" }] };
    useMarkStore.getState().edit("finding:spot:0", spot);
    useMarkStore.getState().setNextKind("smooth");
    expect(kinds()).toEqual(["smooth"]);
    expect(undoHasSomewhereToGo(useMarkStore.getState())).toBe(false);
    expect(hasUnkeptLine(useMarkStore.getState())).toBe(false);
  });
});
