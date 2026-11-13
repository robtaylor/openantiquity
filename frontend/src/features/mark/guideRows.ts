/**
 * What the drawing guide on the map lists: the gestures that apply now, as
 * the marking stands and for the device in hand, each with its icon, the
 * gesture and what it does. Every row is true of the tool's code at that
 * moment, and a gesture the tool doesn't offer then has no row. Nothing
 * here knows about React or the map: `DrawingGuide` draws the rows.
 */

import { endWord, otherEnd, type Path, type PathEnd, type PointKind } from "./path.js";

/** The state of a marking, as the guide names it. */
export type MarkingStage = "empty" | "spot" | "line" | "shape";

export function stageOf(path: Path): MarkingStage {
  if (path.points.length === 0) return "empty";
  if (path.closed) return "shape";
  return path.points.length === 1 ? "spot" : "line";
}

/** The device in hand: a pointer's gestures, a finger's, or the keys once the map or a point has keyboard focus. */
export type Device = "computer" | "phone" | "keys";

/** Where the browser keeps whether the guide is folded: "folded" or "open". */
export const GUIDE_FOLDED_KEY = "fieldclub.mark.guide";

/** At most this many rows at once, so the card stays short over the map. */
export const GUIDE_MAX_ROWS = 6;

export type GuideIcon =
  | "click"
  | "tap"
  | "again"
  | "close"
  | "move"
  | "dot"
  | "curved"
  | "straight"
  | "switch"
  | "select"
  | "end"
  | "keys-move"
  | "keys-pan"
  | "keys-further"
  | "keys-step"
  | "keys-delete"
  | "keys-stop"
  | "keys-leave"
  | "cross";

/** A gesture's words, with any key in it shown as a key. */
export type GesturePart = string | { key: string };

export interface GuideRow {
  id: string;
  icon: GuideIcon;
  gesture: readonly GesturePart[];
  effect: string;
}

export interface GuideState {
  stage: MarkingStage;
  /** True while taps on the map add points. */
  drawing: boolean;
  device: Device;
  /** The kind a tap adds, as chosen on the drawing bar. */
  nextKind: PointKind;
  /** The end of an open path a tap adds to. */
  end: PathEnd;
  /** True when a tap on the far end would close the shape: an open path of three points or more. */
  canClose: boolean;
  /** True when a midpoint dot is drawn on the map now. */
  dots: boolean;
}

/** A gesture's words with its keys written out, as a screen reader and a test read them. */
export function gestureText(row: GuideRow): string {
  return row.gesture.map((part) => (typeof part === "string" ? part : part.key)).join("");
}

function key(name: string): GesturePart {
  return { key: name };
}

function keyRows(state: GuideState): GuideRow[] {
  const leave: GuideRow = { id: "leave", icon: "keys-leave", gesture: [key("Esc")], effect: "Closes the tool" };
  const pan: GuideRow = {
    id: "pan",
    icon: "keys-pan",
    gesture: [key("Arrow keys"), " on the map"],
    effect: "Slide the map under the cross",
  };
  const cross: GuideRow = {
    id: "cross",
    icon: "cross",
    gesture: ["“Add a point at the cross”"],
    effect: "Puts a point there",
  };
  if (state.stage === "empty") return [pan, cross, leave];
  const nudge: GuideRow = {
    id: "nudge",
    icon: "keys-move",
    gesture: [key("Arrow keys"), " on a point"],
    effect: "Move it",
  };
  const step: GuideRow = {
    id: "step",
    icon: "keys-step",
    gesture: [key("["), " and ", key("]")],
    effect: "Step between points",
  };
  const remove: GuideRow = { id: "delete", icon: "keys-delete", gesture: [key("Delete")], effect: "Removes the point" };
  if (state.drawing) {
    // While drawing, how to add the next point matters more than Shift's bigger step.
    const stop: GuideRow = {
      id: "stop",
      icon: "keys-stop",
      gesture: [key("Enter"), " or ", key("Esc")],
      effect: "Stops adding points",
    };
    return [nudge, step, remove, pan, cross, stop];
  }
  const further: GuideRow = {
    id: "further",
    icon: "keys-further",
    gesture: [key("Shift"), " and an arrow key"],
    effect: "Moves it further",
  };
  return [nudge, further, step, remove, leave];
}

function pointerRows(state: GuideState): GuideRow[] {
  const phone = state.device === "phone";
  const tap = phone ? "Tap" : "Click";
  const icon = phone ? "tap" : "click";
  const one = state.stage === "spot";
  const which = one ? "the point" : "a point";
  const other: PointKind = state.nextKind === "corner" ? "smooth" : "corner";
  const otherWord = other === "smooth" ? "curved" : "straight";
  const switchRow: GuideRow = phone
    ? {
        id: "switch",
        icon: "switch",
        gesture: [`Press and hold ${which}`],
        effect: "Switches it between straight and curved",
      }
    : {
        id: "switch",
        icon: "switch",
        gesture: [key("Shift"), `-click ${which}`],
        effect: "Switches it between straight and curved",
      };
  const move: GuideRow = { id: "move", icon: "move", gesture: [`Drag ${which}`], effect: "Moves it" };
  const select: GuideRow = {
    id: "select",
    icon: "select",
    gesture: [`${tap} ${which}`],
    effect: "Selects it, to delete it",
  };
  const dot: GuideRow = {
    id: "dot",
    icon: "dot",
    gesture: ["Drag a dot on the line"],
    effect: "Adds a point there to bend it",
  };

  if (state.stage === "empty") {
    return [
      { id: "start", icon, gesture: [`${tap} the map`], effect: "Marks a spot where the feature is" },
      { id: "again", icon: "again", gesture: [`${tap} again`], effect: "Draws a line from it" },
    ];
  }

  const rows: GuideRow[] = [];
  if (state.drawing && one) {
    rows.push({ id: "again", icon: "again", gesture: [`${tap} again`], effect: "Draws a line from the spot" });
    rows.push(move);
    if (phone) rows.push(switchRow);
    else
      rows.push({
        id: "other",
        icon: otherWord,
        gesture: [key("Shift"), "-click"],
        effect: `Adds a ${otherWord} point`,
      });
    rows.push(select);
    return rows;
  }

  if (state.drawing) {
    rows.push({ id: "add", icon, gesture: [`${tap} the map`], effect: "Adds the next point" });
    if (state.canClose) {
      rows.push({
        id: "close",
        icon: "close",
        gesture: [`${tap} the ${endWord(otherEnd(state.end))} point`],
        effect: "Closes it into a shape",
      });
    }
    rows.push(move);
    if (state.dots) rows.push(dot);
    if (phone) rows.push(switchRow);
    else {
      rows.push({
        id: "other",
        icon: otherWord,
        gesture: [key("Shift"), "-click"],
        effect: `Adds a ${otherWord} point, or on a point switches its kind`,
      });
    }
    rows.push(select);
    return rows;
  }

  // Drawing has stopped, or the shape is closed: what can still be changed.
  rows.push(move);
  if (state.dots) rows.push(dot);
  rows.push(switchRow);
  if (one) {
    rows.push({ ...select, effect: "Selects it, to delete it or draw a line" });
    return rows;
  }
  rows.push(select);
  // An open path's ends have "Continue from this end" on the selected point's bar.
  if (state.stage === "line") {
    rows.push({ id: "end", icon: "end", gesture: [`${tap} an end point`], effect: "Lets you draw on from there" });
  }
  return rows;
}

/** The rows for the marking as it stands, at most `GUIDE_MAX_ROWS`. */
export function guideRows(state: GuideState): GuideRow[] {
  const rows = state.device === "keys" ? keyRows(state) : pointerRows(state);
  if (rows.length > GUIDE_MAX_ROWS) throw new RangeError(`The guide has ${rows.length} rows, over ${GUIDE_MAX_ROWS}`);
  return rows;
}
