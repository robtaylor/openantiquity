/**
 * The finding being marked: its path, the drawing tool's state, and the
 * rest of the form. The panel (`MarkPanel`) and the map layer (`MarkLayer`)
 * share it, so a drag on the map and a field in the panel are one piece of
 * state.
 *
 * Marking is one flow (Decision 0031). The first tap places a point, which
 * alone is a finding at a spot. Each further tap adds a point at the active
 * end, and a tap on the far end closes the shape. A tap always adds a point;
 * a point is moved by dragging its handle.
 *
 * Nothing here is stored. Pressing save turns it into a request, or into a
 * draft when nobody is signed in (`findingDrafts`).
 */

import { create } from "zustand";
import type { ShapeLimits } from "../../api/meta.js";
import type { PositionField } from "../finding/positionInText.js";
import type { MarkProblemField } from "./compose.js";
import type { FindingDraft } from "./findingDrafts.js";
import {
  addPoint,
  closePath,
  commit,
  deletePoint,
  EMPTY_PATH,
  endIndex,
  type History,
  history,
  insertAfter,
  insertAt,
  type LngLat,
  movePoint,
  type Path,
  type PathEnd,
  type PointKind,
  redo,
  replace,
  setKind,
  switchKind,
  undo,
} from "./path.js";

/** The period a new finding has until the finder says otherwise. */
export const UNKNOWN_PERIOD = "unknown";

export interface MarkFields {
  /** The draft being edited, or null for a new mark. */
  draftId: string | null;
  /** The path and the states undo and redo step through. */
  shape: History<Path>;
  /** Which end of an open path a tap adds to. */
  end: PathEnd;
  /** The kind of point a tap adds, as set on the drawing bar. */
  nextKind: PointKind;
  /** The point whose bar is showing, or null. */
  selected: number | null;
  /** True while taps on the map add points. Finish or Escape stops it, keeping the path. */
  drawing: boolean;
  /** True when the last point added came from "Add a point at the cross", not a tap. */
  crossAdded: boolean;
  featureClass: string | null;
  period: string;
  /** What the finder typed. Empty means the suggested title. */
  title: string;
  note: string;
  /** What stops it being saved, in plain words, and which part of the form it is about, until that part changes. */
  problem: { field: MarkProblemField; message: string } | null;
  /** The title or note the server refused for saying where it is more closely than its square, until each changes. */
  placed: readonly PositionField[];
  /** True while the save is on its way. */
  saving: boolean;
}

export interface MarkState extends MarkFields {
  /** Start afresh, with nothing placed and the map taking taps. */
  start: () => void;
  /** Take up a draft to change or save it. */
  load: (draftId: string, draft: FindingDraft) => void;
  /** A tap on the map, or "Add a point at the cross": a point of the chosen kind, or the other with `otherKind`. */
  add: (point: LngLat, limits: ShapeLimits, otherKind?: boolean) => void;
  /** "Add a point at the cross": a point of the chosen kind, noted as placed by the button. */
  addAtCross: (point: LngLat, limits: ShapeLimits) => void;
  /** Insert a point where the line is, after point `index`: an Alt-click on a segment. */
  insertOnSegment: (index: number, point: LngLat) => void;
  /**
   * Move a point. The first step of a drag is recorded for undo, and the
   * steps after it, with `continuing`, replace it, so one drag is one undo.
   */
  move: (index: number, point: LngLat, continuing?: boolean) => void;
  remove: (index: number) => void;
  setPointKind: (index: number, kind: PointKind) => void;
  switchPointKind: (index: number) => void;
  insertAfterPoint: (index: number) => void;
  setNextKind: (kind: PointKind) => void;
  select: (index: number | null) => void;
  closeShape: () => void;
  /** Stop adding points, keeping the path. */
  finish: () => void;
  /** Make one end of an open path the active one and go on adding there. */
  continueFrom: (end: PathEnd) => void;
  undo: () => void;
  redo: () => void;
  setFeatureClass: (id: string) => void;
  setPeriod: (id: string) => void;
  setTitle: (title: string) => void;
  setNote: (note: string) => void;
  setProblem: (problem: { field: MarkProblemField; message: string } | null) => void;
  setPlaced: (placed: readonly PositionField[]) => void;
  setSaving: (saving: boolean) => void;
}

export const EMPTY_MARK: MarkFields = {
  draftId: null,
  shape: history(EMPTY_PATH),
  end: "end",
  nextKind: "corner",
  selected: null,
  drawing: true,
  crossAdded: false,
  featureClass: null,
  period: UNKNOWN_PERIOD,
  title: "",
  note: "",
  problem: null,
  placed: [],
  saving: false,
};

/** The path a draft holds: its line or shape, or its one point. */
function pathFrom(draft: FindingDraft): Path {
  if (draft.path) return { closed: draft.path.closed, points: draft.path.points };
  return { closed: false, points: [{ lon: draft.point[0], lat: draft.point[1], kind: "corner" }] };
}

/** The selection kept by a change, or none when the point it names has gone. */
function keptSelection(selected: number | null, path: Path): number | null {
  return selected !== null && selected < path.points.length ? selected : null;
}

export const useMarkStore = create<MarkState>()((set, get) => {
  /** The problem, unless it was about `field`, which has just changed. */
  function problemAfter(field: MarkProblemField): MarkFields["problem"] {
    const { problem } = get();
    return problem?.field === field ? null : problem;
  }

  /** A change to the path, recorded for undo unless `continuing` a drag. */
  function change(next: (path: Path) => Path, extra: Partial<MarkFields> = {}, continuing = false): void {
    const { shape } = get();
    const path = next(shape.present);
    const shapeAfter = continuing ? replace(shape, path) : commit(shape, path);
    if (shapeAfter === shape && Object.keys(extra).length === 0) return;
    // A change to the path or the point may settle a problem with either.
    const problem = problemAfter("path");
    set({
      shape: shapeAfter,
      problem: problem?.field === "point" ? null : problem,
      ...extra,
    });
  }

  return {
    ...EMPTY_MARK,

    start: () => set({ ...EMPTY_MARK }),

    load: (draftId, draft) =>
      set({
        ...EMPTY_MARK,
        draftId,
        shape: history(pathFrom(draft)),
        drawing: false,
        featureClass: draft.feature_class,
        period: draft.period,
        title: draft.title,
        note: draft.description ?? "",
      }),

    add: (point, limits, otherKind = false) => {
      const { nextKind, end, drawing } = get();
      if (!drawing) return;
      const kind: PointKind = otherKind ? (nextKind === "corner" ? "smooth" : "corner") : nextKind;
      change((path) => addPoint(path, { lon: point[0], lat: point[1], kind }, end, limits), {
        selected: null,
        crossAdded: false,
      });
    },
    addAtCross: (point, limits) => {
      const { nextKind, end, drawing } = get();
      if (!drawing) return;
      change((path) => addPoint(path, { lon: point[0], lat: point[1], kind: nextKind }, end, limits), {
        selected: null,
        crossAdded: true,
      });
    },
    insertOnSegment: (index, point) => change((path) => insertAt(path, index, point), { selected: index + 1 }),
    move: (index, point, continuing = false) => change((path) => movePoint(path, index, point), {}, continuing),
    remove: (index) => {
      const after = deletePoint(get().shape.present, index);
      const selected = after.points.length === 0 ? null : Math.min(index, after.points.length - 1);
      change(() => after, { selected: after.points.length > 1 ? selected : null });
    },
    setPointKind: (index, kind) => change((path) => setKind(path, index, kind)),
    switchPointKind: (index) => change((path) => switchKind(path, index)),
    insertAfterPoint: (index) => {
      const before = get().shape.present;
      const after = insertAfter(before, index);
      if (after !== before) change(() => after, { selected: index + 1 });
    },
    setNextKind: (nextKind) => set({ nextKind }),
    select: (selected) => set({ selected }),
    closeShape: () => change(closePath, { drawing: false, selected: null }),
    finish: () => set({ drawing: false }),
    continueFrom: (end) => {
      const path = get().shape.present;
      if (path.closed || path.points.length === 0) return;
      set({ end, drawing: true, selected: endIndex(path, end) });
    },
    undo: () => {
      const before = get().shape;
      const shape = undo(before);
      // Undoing a close opens the shape again for drawing.
      const reopened = before.present.closed && !shape.present.closed;
      set((state) => ({
        shape,
        selected: keptSelection(state.selected, shape.present),
        drawing: state.drawing || reopened,
      }));
    },
    redo: () => {
      const shape = redo(get().shape);
      set((state) => ({ shape, selected: keptSelection(state.selected, shape.present) }));
    },

    setFeatureClass: (featureClass) => set({ featureClass, problem: problemAfter("featureClass") }),
    setPeriod: (period) => set({ period }),
    setTitle: (title) => set((state) => ({ title, placed: state.placed.filter((field) => field !== "title") })),
    setNote: (note) => set((state) => ({ note, placed: state.placed.filter((field) => field !== "description") })),

    setProblem: (problem) => set({ problem }),
    setPlaced: (placed) => set({ placed }),
    setSaving: (saving) => set({ saving }),
  };
});

/** True while taps add points: drawing, and the shape not closed. */
export function isAdding(state: MarkFields): boolean {
  return state.drawing && !state.shape.present.closed;
}

/** The path being marked, for components. */
export function useMarkPath(): Path {
  return useMarkStore((state) => state.shape.present);
}
