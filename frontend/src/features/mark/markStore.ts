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
 * draft when nobody is signed in (`findingDrafts`). It may hold a saved
 * finding's exact path ("Change the shape") or a kept draft, and forgets
 * either when the person changes, as every store of exact places does
 * (`onPersonChanged`). A marking never kept stays.
 */

import { create } from "zustand";
import type { ShapeLimits } from "../../api/meta.js";
import { onPersonChanged } from "../account/session.js";
import type { PositionField } from "../finding/positionInText.js";
import type { MarkProblemField } from "./compose.js";
import { editedFinding } from "./editingKey.js";
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
  insertMidpoint,
  type LngLat,
  movePoint,
  oppositeKind,
  type Path,
  type PathEnd,
  type PointKind,
  redo,
  replace,
  setKind,
  spotPath,
  switchKind,
  undo,
} from "./path.js";

/** The period a new finding has until the finder says otherwise. */
export const UNKNOWN_PERIOD = "unknown";

export interface MarkFields {
  /** The draft being edited, or null for a new mark. */
  draftId: string | null;
  /**
   * What the path was taken up from, as the caller named it, such as a saved
   * finding whose shape is being changed. The tool doesn't read it: it only
   * lets the caller tell its own path from another.
   */
  editing: string | null;
  /** The path and the states undo and redo step through. */
  shape: History<Path>;
  /**
   * The path as it was last kept: a draft's as it was taken up or kept, a
   * saved finding's as it was taken up. Null for a new mark. While the path
   * is another, it is only here, and leaving the page loses it.
   */
  kept: Path | null;
  /** Which end of an open path a tap adds to. */
  end: PathEnd;
  /** The kind of point a tap adds, as set on the drawing bar. A first point placed alone takes it too. */
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
  /**
   * True while the marking in hand is set aside: the tool was opened with the
   * map somewhere else, and the person hasn't yet said whether to go back to
   * it. It isn't drawn as being worked on, and a tap adds nothing to it.
   */
  setAside: boolean;
}

export interface MarkState extends MarkFields {
  /** Start afresh, with nothing placed and the map taking taps. */
  start: () => void;
  /** Take up a draft to change or save it. */
  load: (draftId: string, draft: FindingDraft) => void;
  /** The path as it is now has been kept as draft `draftId`. */
  keptAs: (draftId: string) => void;
  /** Take up a path to change, named `editing` by the caller, with nothing selected and no points being added. */
  edit: (editing: string, path: Path) => void;
  /**
   * Name what the tool holds `editing` instead, keeping the path, its undo
   * and everything else: a change carried over to a newer revision of the
   * shape, or from a suggestion to a change, at the person's word.
   */
  rename: (editing: string) => void;
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
  switchPointKind: (index: number) => void;
  insertAfterPoint: (index: number) => void;
  /**
   * A midpoint dot: insert a point half way along the segment after point
   * `index`, held to the limits, and select it when `select`. A drag carries
   * on with `move(index + 1, …, true)`, so the insert and the drag are one
   * step to undo, and keeps what was selected, its index moved past the new
   * point. False when nothing was inserted.
   */
  insertMidpoint: (index: number, limits: ShapeLimits, select: boolean) => boolean;
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
  editing: null,
  shape: history(EMPTY_PATH),
  kept: null,
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
  setAside: false,
};

/** The path a draft holds: its line or shape, or its one point. */
function pathFrom(draft: FindingDraft): Path {
  if (draft.path) return { closed: draft.path.closed, points: draft.path.points };
  return spotPath(draft.point);
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

  /** A point at the active end, of the chosen kind or the other, noting whether the cross placed it. */
  function addAtEnd([lon, lat]: LngLat, limits: ShapeLimits, otherKind: boolean, crossAdded: boolean): void {
    const { nextKind, end, drawing } = get();
    if (!drawing) return;
    const kind = otherKind ? oppositeKind(nextKind) : nextKind;
    change((path) => addPoint(path, { lon, lat, kind }, end, limits), { selected: null, crossAdded });
  }

  return {
    ...EMPTY_MARK,

    start: () => set({ ...EMPTY_MARK }),

    load: (draftId, draft) => {
      const path = pathFrom(draft);
      set({
        ...EMPTY_MARK,
        draftId,
        shape: history(path),
        kept: path,
        drawing: false,
        featureClass: draft.feature_class,
        period: draft.period,
        title: draft.title,
        note: draft.description ?? "",
      });
    },

    edit: (editing, path) => set({ ...EMPTY_MARK, editing, shape: history(path), kept: path, drawing: false }),

    rename: (editing) => set({ editing }),

    keptAs: (draftId) => set((state) => ({ draftId, kept: state.shape.present })),

    add: (point, limits, otherKind = false) => addAtEnd(point, limits, otherKind, false),
    addAtCross: (point, limits) => addAtEnd(point, limits, false, true),
    insertOnSegment: (index, point) => change((path) => insertAt(path, index, point), { selected: index + 1 }),
    move: (index, point, continuing = false) => change((path) => movePoint(path, index, point), {}, continuing),
    remove: (index) => {
      const after = deletePoint(get().shape.present, index);
      const selected = after.points.length === 0 ? null : Math.min(index, after.points.length - 1);
      // With nothing left, taps add a point again, as when marking starts.
      const emptied = after.points.length === 0 ? { drawing: true, end: "end" as const } : {};
      change(() => after, { selected: after.points.length > 1 ? selected : null, ...emptied });
    },
    switchPointKind: (index) => change((path) => switchKind(path, index)),
    insertAfterPoint: (index) => {
      const before = get().shape.present;
      const after = insertAfter(before, index);
      if (after !== before) change(() => after, { selected: index + 1 });
    },
    insertMidpoint: (index, limits, select) => {
      const before = get().shape.present;
      if (index < 0 || index >= before.points.length) return false;
      const after = insertMidpoint(before, index, limits);
      if (after === before) return false;
      // A drag keeps what was selected, so a phone's bars don't swap under the finger. Its index moves on past the new point.
      const { selected } = get();
      const kept = selected !== null && selected > index ? selected + 1 : selected;
      change(() => after, { selected: select ? index + 1 : kept });
      return true;
    },
    setNextKind: (nextKind) => {
      // The first tap comes before its finder has said which kind they want,
      // and a lone point's kind shows only once a shape closes on it. So
      // while it is the only point it follows the choice, and undo has
      // nothing more to step through for it.
      const alone = get().shape.present.points.length === 1;
      change((path) => (alone ? setKind(path, 0, nextKind) : path), { nextKind }, true);
    },
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

// A saved finding's path is something one viewer was allowed to see, and a
// kept draft is one person's: both go, and the panel loads again a draft that
// is still this person's. A marking that was never kept is the work of
// whoever is at the screen, drawn perhaps before they signed in, and stays.
onPersonChanged(() => {
  const { editing, draftId } = useMarkStore.getState();
  if (editing !== null || draftId !== null) useMarkStore.getState().start();
});

/** True while taps add points: drawing, and the shape not closed. */
export function isAdding(state: MarkFields): boolean {
  return state.drawing && !state.shape.present.closed;
}

/**
 * True while the tool holds a new marking, of one point or more, that is
 * neither a saved finding's path nor a kept draft. Opening the tool again
 * carries on with it, where it would otherwise start afresh.
 */
export function isUnsavedNewMark(state: MarkFields): boolean {
  return state.editing === null && state.draftId === null && state.shape.present.points.length > 0;
}

/** True while a line or a shape is drawn that isn't saved or kept as a draft, which leaving the page would lose. */
export function hasUnkeptLine(state: MarkFields): boolean {
  const path = state.shape.present;
  return path.points.length >= 2 && path !== state.kept;
}

/**
 * Something unsaved the tool holds: a new marking, a change to a saved
 * finding's shape, a suggested change to someone else's that isn't sent, or
 * a draft whose line has changed since it was kept. A panel that would take
 * the tool over asks before it does, and one that closes without having
 * taken it over leaves it alone.
 */
export type Unsaved =
  | { kind: "marking" }
  | { kind: "change"; publicId: string }
  | { kind: "suggestion"; publicId: string }
  | { kind: "draft"; draftId: string };

export function unsavedInHand(state: MarkFields): Unsaved | null {
  if (isUnsavedNewMark(state)) return { kind: "marking" };
  const publicId = editedFinding(state.editing);
  if (publicId !== null) return state.shape.past.length > 0 ? { kind: "change", publicId } : null;
  const suggested = unsentSuggestion(state);
  if (suggested !== null) return { kind: "suggestion", publicId: suggested };
  // A draft as it was kept is safe where it is kept. Its title and note aren't looked at: only its line.
  if (state.draftId !== null && hasUnkeptLine(state)) return { kind: "draft", draftId: state.draftId };
  return null;
}

/**
 * The finding a suggested change in hand is for, once something has been
 * changed: a suggestion taken up and left as it was loses nothing. Like a
 * new marking, it is kept in sight while the tool isn't on it.
 */
export function unsentSuggestion(state: MarkFields): string | null {
  const publicId = editedFinding(state.editing, "suggest");
  return publicId !== null && state.shape.past.length > 0 ? publicId : null;
}

/** `unsavedInHand` as text, so a component can follow it without a new object each time. */
export function unsavedKey(state: MarkFields): string | null {
  const held = unsavedInHand(state);
  if (held === null) return null;
  return held.kind === "marking" ? "marking" : `${held.kind}:${held.kind === "draft" ? held.draftId : held.publicId}`;
}

/** The path being marked, for components. */
export function useMarkPath(): Path {
  return useMarkStore((state) => state.shape.present);
}
