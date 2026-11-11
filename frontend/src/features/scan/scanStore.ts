/**
 * Where the person is in "Scan a square": the square up now, when they
 * started on it, what they made of it, and the squares done in this visit.
 * It lives outside the panel because the shell takes the panel away while
 * the layer panel is open over it, or while a finding is being marked, and
 * neither ends a scan (docs/UI.md, "Layout").
 *
 * It is kept in this tab's `sessionStorage` too, so a provider's sign-in,
 * which reloads the page, comes back to the same square with the count of
 * squares done. A square is a public one-kilometre grid square, and the
 * store holds nothing else about anyone.
 */

import { create } from "zustand";
import { isFiniteNumber, isRecord } from "../../api/guards.js";
import type { Square, SurveyResult } from "./api.js";

export const SCAN_STORAGE_KEY = "fieldclub.scan";

/** A square the person has said how it went, in this visit. */
export interface DoneSquare {
  square: string;
  grid_ref: string;
  result: Exclude<SurveyResult, "skipped">;
}

export interface ScanState {
  /** Bumped each time a new square is asked for. Zero until the first. */
  ticket: number;
  /** Where the map was when the square was asked for. */
  near: [number, number] | null;
  current: Square | null;
  /** When the current square came up, in milliseconds since 1970. */
  startedAt: number | null;
  /** What the person made of the current square, once they have said. */
  finished: DoneSquare | null;
  /** Squares done in this visit, oldest first: the running count. Skips aren't among them. */
  done: readonly DoneSquare[];
  /** Every square finished, skipped or passed over in this visit, so none comes up twice. */
  passed: readonly string[];

  /** Ask for a new square near `near`. */
  ask: (near: [number, number] | null) => void;
  show: (square: Square) => void;
  /** The person has said how the current square went. */
  finish: (done: DoneSquare) => void;
  /** A result the server refused: it no longer counts, and the square may come up again. */
  undo: (square: string) => void;
  /** Leave the current square without a result. */
  pass: () => void;
  reset: () => void;
}

const FRESH = {
  ticket: 0,
  near: null,
  current: null,
  startedAt: null,
  finished: null,
  done: [],
  passed: [],
} satisfies Partial<ScanState>;

type Kept = Pick<ScanState, "current" | "startedAt" | "finished" | "done" | "passed">;

function isDone(value: unknown): value is DoneSquare {
  return (
    isRecord(value) &&
    typeof value.square === "string" &&
    typeof value.grid_ref === "string" &&
    (value.result === "nothing" || value.result === "marked")
  );
}

function isSquare(value: unknown): value is Square {
  return (
    isRecord(value) &&
    typeof value.square === "string" &&
    typeof value.grid_ref === "string" &&
    isFiniteNumber(value.scans) &&
    Array.isArray(value.bbox) &&
    value.bbox.length === 4 &&
    value.bbox.every(isFiniteNumber) &&
    Array.isArray(value.centre) &&
    isRecord(value.geometry)
  );
}

/** What was kept over a reload, if it can be read. Anything odd is dropped. */
export function parseKept(raw: string | null): Kept | null {
  if (raw === null) return null;
  try {
    const value: unknown = JSON.parse(raw);
    if (!isRecord(value)) return null;
    const current = isSquare(value.current) ? value.current : null;
    return {
      current,
      startedAt: current !== null && isFiniteNumber(value.startedAt) ? value.startedAt : null,
      finished: current !== null && isDone(value.finished) ? value.finished : null,
      done: Array.isArray(value.done) ? value.done.filter(isDone) : [],
      passed: Array.isArray(value.passed)
        ? value.passed.filter((square): square is string => typeof square === "string")
        : [],
    };
  } catch {
    return null;
  }
}

function readKept(): Kept | null {
  try {
    return parseKept(sessionStorage.getItem(SCAN_STORAGE_KEY));
  } catch {
    return null;
  }
}

function keep(state: Kept): void {
  try {
    const { current, startedAt, finished, done, passed } = state;
    sessionStorage.setItem(SCAN_STORAGE_KEY, JSON.stringify({ current, startedAt, finished, done, passed }));
  } catch {
    // A browser that won't store it starts the scan afresh after a reload. Drafts are kept either way.
  }
}

export const useScanStore = create<ScanState>()((set, get) => ({
  ...FRESH,
  ...readKept(),

  ask: (near) => set((state) => ({ ticket: state.ticket + 1, near, current: null, startedAt: null, finished: null })),
  show: (square) => set({ current: square, startedAt: Date.now(), finished: null }),
  finish: (done) =>
    set((state) => ({
      finished: state.current?.square === done.square ? done : state.finished,
      done: [...state.done.filter((entry) => entry.square !== done.square), done],
      passed: state.passed.includes(done.square) ? state.passed : [...state.passed, done.square],
    })),
  undo: (square) =>
    set((state) => ({
      finished: state.finished?.square === square ? null : state.finished,
      done: state.done.filter((entry) => entry.square !== square),
      passed: state.passed.filter((entry) => entry !== square),
    })),
  pass: () => {
    const { current, passed } = get();
    if (current && !passed.includes(current.square)) set({ passed: [...passed, current.square] });
  },
  reset: () => set({ ...FRESH }),
}));

useScanStore.subscribe((next, previous) => {
  if (
    next.current !== previous.current ||
    next.finished !== previous.finished ||
    next.done !== previous.done ||
    next.passed !== previous.passed
  ) {
    keep(next);
  }
});
