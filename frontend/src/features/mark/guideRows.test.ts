// @vitest-environment node
import { describe, expect, it } from "vitest";
import { GUIDE_MAX_ROWS, type GuideRow, type GuideState, gestureText, guideRows } from "./guideRows.js";

const BASE: GuideState = {
  stage: "empty",
  drawing: true,
  device: "computer",
  nextKind: "corner",
  end: "end",
  canClose: false,
  dots: false,
};

function lines(state: Partial<GuideState>): string[] {
  return guideRows({ ...BASE, ...state }).map((row) => `${gestureText(row)}: ${row.effect}`);
}

function keysOf(rows: GuideRow[]): string[] {
  return rows.flatMap((row) => row.gesture.flatMap((part) => (typeof part === "string" ? [] : [part.key])));
}

describe("the rows of the drawing guide", () => {
  it("starts a marking: a tap or a click on the map marks a spot", () => {
    expect(lines({})).toEqual([
      "Click the map: Marks a spot where the feature is",
      "Click again: Draws a line from it",
    ]);
    expect(lines({ device: "phone" })).toEqual([
      "Tap the map: Marks a spot where the feature is",
      "Tap again: Draws a line from it",
    ]);
  });

  it("carries a spot on into a line, and says how to move it", () => {
    expect(lines({ stage: "spot" })).toEqual([
      "Click again: Draws a line from the spot",
      "Drag the point: Moves it",
      "Shift-click: Adds a curved point",
      "Click the point: Selects it, to delete it",
    ]);
    expect(lines({ stage: "spot", device: "phone", nextKind: "smooth" })).toEqual([
      "Tap again: Draws a line from the spot",
      "Drag the point: Moves it",
      "Press and hold the point: Switches it between straight and curved",
      "Tap the point: Selects it, to delete it",
    ]);
  });

  it("names every gesture of a line being drawn on a computer, six at most", () => {
    expect(lines({ stage: "line", canClose: true, dots: true })).toEqual([
      "Click the map: Adds the next point",
      "Click the first point: Closes it into a shape",
      "Drag a point: Moves it",
      "Drag a dot on the line: Adds a point there to bend it",
      "Shift-click: Adds a curved point, or on a point switches its kind",
      "Click a point: Selects it, to delete it",
    ]);
    // The other kind is the one not chosen on the bar, and the far end is the one not being drawn from.
    expect(lines({ stage: "line", canClose: true, nextKind: "smooth", end: "start" })).toEqual([
      "Click the map: Adds the next point",
      "Click the last point: Closes it into a shape",
      "Drag a point: Moves it",
      "Shift-click: Adds a straight point, or on a point switches its kind",
      "Click a point: Selects it, to delete it",
    ]);
  });

  it("names a phone's gestures for a line being drawn", () => {
    expect(lines({ stage: "line", device: "phone", canClose: true, dots: true })).toEqual([
      "Tap the map: Adds the next point",
      "Tap the first point: Closes it into a shape",
      "Drag a point: Moves it",
      "Drag a dot on the line: Adds a point there to bend it",
      "Press and hold a point: Switches it between straight and curved",
      "Tap a point: Selects it, to delete it",
    ]);
  });

  it("leaves out closing until there are three points, and the dots when there is no room for a point", () => {
    const rows = lines({ stage: "line", device: "phone" });
    expect(rows.some((row) => row.includes("Closes it"))).toBe(false);
    expect(rows.some((row) => row.includes("dot"))).toBe(false);
  });

  it("names what can still be changed once drawing stops, or the shape is closed", () => {
    expect(lines({ stage: "line", drawing: false, dots: true })).toEqual([
      "Drag a point: Moves it",
      "Drag a dot on the line: Adds a point there to bend it",
      "Shift-click a point: Switches it between straight and curved",
      "Click a point: Selects it, to delete it",
      "Click an end point: Lets you draw on from there",
    ]);
    expect(lines({ stage: "shape", drawing: false, device: "phone", dots: true })).toEqual([
      "Drag a point: Moves it",
      "Drag a dot on the line: Adds a point there to bend it",
      "Press and hold a point: Switches it between straight and curved",
      "Tap a point: Selects it, to delete it",
    ]);
    expect(lines({ stage: "spot", drawing: false })).toEqual([
      "Drag the point: Moves it",
      "Shift-click the point: Switches it between straight and curved",
      "Click the point: Selects it, to delete it or draw a line",
    ]);
  });

  it("names the keys, as keys, once the map or a point has keyboard focus", () => {
    const drawing = guideRows({ ...BASE, stage: "line", device: "keys" });
    expect(drawing.map((row) => `${gestureText(row)}: ${row.effect}`)).toEqual([
      "Arrow keys on a point: Move it",
      "Shift and an arrow key: Moves it further",
      "[ and ]: Step between points",
      "Delete: Removes the point",
      "Enter or Esc: Stops adding points",
    ]);
    expect(keysOf(drawing)).toEqual(["Arrow keys", "Shift", "[", "]", "Delete", "Enter", "Esc"]);
    expect(lines({ stage: "shape", drawing: false, device: "keys" }).at(-1)).toBe("Esc: Closes the tool");
    expect(lines({ device: "keys" })).toEqual([
      "Arrow keys on the map: Move it under the cross",
      "“Add a point at the cross”: Puts a point there",
      "Esc: Closes the tool",
    ]);
  });

  it("never shows more than six rows", () => {
    for (const stage of ["empty", "spot", "line", "shape"] as const) {
      for (const device of ["computer", "phone", "keys"] as const) {
        for (const drawing of [true, false]) {
          const rows = guideRows({ ...BASE, stage, device, drawing, canClose: true, dots: true });
          expect(rows.length).toBeGreaterThan(0);
          expect(rows.length).toBeLessThanOrEqual(GUIDE_MAX_ROWS);
          expect(new Set(rows.map((row) => row.id)).size).toBe(rows.length);
        }
      }
    }
  });
});
