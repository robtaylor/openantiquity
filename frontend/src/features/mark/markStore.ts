/**
 * The finding being marked: where it is, what it looks like, and the rest
 * of the form. The panel (`MarkPanel`) and the map layer (`MarkLayer`) share
 * it, so a drag on the map and a field in the panel are one piece of state.
 *
 * Nothing here is stored. Pressing save turns it into a request, or into a
 * draft when nobody is signed in (`findingDrafts`).
 */

import { create } from "zustand";
import type { PositionField } from "../finding/positionInText.js";
import type { MarkProblemField } from "./compose.js";
import type { FindingDraft } from "./findingDrafts.js";
import {
  addPoint,
  closeShape,
  finishLine,
  type LngLat,
  NEW_OUTLINE,
  type Outline,
  outlineGeometry,
  undoPoint,
} from "./outline.js";

/** The period a new finding has until the finder says otherwise. */
export const UNKNOWN_PERIOD = "unknown";

export interface MarkFields {
  /** The draft being edited, or null for a new mark. */
  draftId: string | null;
  point: LngLat | null;
  featureClass: string | null;
  period: string;
  /** What the finder typed. Empty means the suggested title. */
  title: string;
  note: string;
  /** The drawn outline, or null for none. */
  outline: Outline | null;
  /** True while the outline tool is taking taps on the map. */
  drawing: boolean;
  /** What stops it being saved, in plain words, and which part of the form it is about, until that part changes. */
  problem: { field: MarkProblemField; message: string } | null;
  /** The title or note the server refused for saying where it is more closely than its square, until each changes. */
  placed: readonly PositionField[];
  /** True while the save is on its way. */
  saving: boolean;
  /**
   * True from a press of "Place it here" until the form has taken focus. The
   * button goes once the mark is down, and focus would otherwise be lost.
   */
  focusForm: boolean;
}

export interface MarkState extends MarkFields {
  /** Start afresh, with nothing placed. */
  start: () => void;
  /** Take up a draft to change or save it. */
  load: (draftId: string, draft: FindingDraft) => void;
  place: (point: LngLat) => void;
  /** Place the mark from a button, so the form takes focus once it is there. */
  placeFromButton: (point: LngLat) => void;
  formFocused: () => void;
  setFeatureClass: (id: string) => void;
  setPeriod: (id: string) => void;
  setTitle: (title: string) => void;
  setNote: (note: string) => void;
  /** Turn the outline tool on, starting a new outline when there is none. */
  startOutline: () => void;
  /** A tap on the map while the outline tool is on. */
  addOutlinePoint: (point: LngLat) => void;
  undoOutlinePoint: () => void;
  closeOutline: () => void;
  finishOutlineLine: () => void;
  /** Stop drawing, keeping what has been drawn. */
  stopDrawing: () => void;
  removeOutline: () => void;
  setProblem: (problem: { field: MarkProblemField; message: string } | null) => void;
  setPlaced: (placed: readonly PositionField[]) => void;
  setSaving: (saving: boolean) => void;
}

export const EMPTY_MARK: MarkFields = {
  draftId: null,
  point: null,
  featureClass: null,
  period: UNKNOWN_PERIOD,
  title: "",
  note: "",
  outline: null,
  drawing: false,
  problem: null,
  placed: [],
  saving: false,
  focusForm: false,
};

/** An outline read back from a draft's GeoJSON, so it can be drawn and changed again. */
function outlineFrom(draft: FindingDraft): Outline | null {
  const geometry = draft.outline;
  if (!geometry || !Array.isArray(geometry.coordinates)) return null;
  const pairs = (values: unknown): LngLat[] =>
    Array.isArray(values)
      ? values.flatMap((value): LngLat[] =>
          Array.isArray(value) && typeof value[0] === "number" && typeof value[1] === "number"
            ? [[value[0], value[1]]]
            : [],
        )
      : [];
  if (geometry.type === "Polygon") {
    const ring = pairs(geometry.coordinates[0]);
    return { points: ring.slice(0, -1), shape: "polygon" };
  }
  if (geometry.type === "LineString") return { points: pairs(geometry.coordinates), shape: "line" };
  return null;
}

export const useMarkStore = create<MarkState>()((set, get) => {
  /** The problem, unless it was about `field`, which has just changed. */
  function problemAfter(field: MarkProblemField): MarkFields["problem"] {
    const { problem } = get();
    return problem?.field === field ? null : problem;
  }

  function changeOutline(change: (outline: Outline) => Outline): void {
    const { outline } = get();
    if (outline) set({ outline: change(outline), problem: problemAfter("outline") });
  }

  return {
    ...EMPTY_MARK,

    start: () => set({ ...EMPTY_MARK }),

    load: (draftId, draft) =>
      set({
        ...EMPTY_MARK,
        draftId,
        point: draft.point,
        featureClass: draft.feature_class,
        period: draft.period,
        title: draft.title,
        note: draft.description ?? "",
        outline: outlineFrom(draft),
      }),

    place: (point) => set({ point, problem: problemAfter("point") }),
    placeFromButton: (point) => set({ point, problem: problemAfter("point"), focusForm: true }),
    formFocused: () => set({ focusForm: false }),
    setFeatureClass: (featureClass) => set({ featureClass, problem: problemAfter("featureClass") }),
    setPeriod: (period) => set({ period }),
    setTitle: (title) => set((state) => ({ title, placed: state.placed.filter((field) => field !== "title") })),
    setNote: (note) => set((state) => ({ note, placed: state.placed.filter((field) => field !== "description") })),

    startOutline: () => set((state) => ({ drawing: true, outline: state.outline ?? NEW_OUTLINE })),
    addOutlinePoint: (point) => changeOutline((outline) => addPoint(outline, point)),
    undoOutlinePoint: () => {
      changeOutline(undoPoint);
      set({ drawing: true });
    },
    closeOutline: () => {
      changeOutline(closeShape);
      set({ drawing: false });
    },
    finishOutlineLine: () => {
      changeOutline(finishLine);
      set({ drawing: false });
    },
    stopDrawing: () => {
      // An outline with too little to it to send is dropped rather than kept half-made.
      const { outline } = get();
      set({ drawing: false, outline: outline && outlineGeometry(outline) ? outline : null });
    },
    removeOutline: () => set({ outline: null, drawing: false, problem: problemAfter("outline") }),

    setProblem: (problem) => set({ problem }),
    setPlaced: (placed) => set({ placed }),
    setSaving: (saving) => set({ saving }),
  };
});
