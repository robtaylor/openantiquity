import { beforeEach, describe, expect, it } from "vitest";
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
