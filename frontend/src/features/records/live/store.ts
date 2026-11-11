import { create } from "zustand";
import type { LiveRecord } from "./parse.js";

/**
 * Which live sources the person has turned on, and how each is doing. Every
 * source starts off, in every page load: a live source is asked only after
 * someone has chosen to see it. A source that fails is switched off again
 * and says why, and stays off until it is turned on by hand.
 */

export type LiveStatus =
  | { state: "idle" }
  | { state: "loading" }
  | { state: "ready"; records: readonly LiveRecord[]; truncated: boolean }
  | { state: "refused" | "failed"; message: string };

const IDLE: LiveStatus = { state: "idle" };

function sameStatus(a: LiveStatus | undefined, b: LiveStatus): boolean {
  if (a === undefined || a.state !== b.state) return false;
  if (a.state === "ready" && b.state === "ready") return a.records === b.records && a.truncated === b.truncated;
  if ((a.state === "refused" || a.state === "failed") && (b.state === "refused" || b.state === "failed")) {
    return a.message === b.message;
  }
  return true;
}

interface LiveState {
  on: Readonly<Record<string, boolean>>;
  status: Readonly<Record<string, LiveStatus>>;
  /** The live record last picked on the map, as `source/id`, so the panel can show it. */
  picked: string | null;
  setOn: (key: string, on: boolean) => void;
  report: (key: string, status: LiveStatus) => void;
  /** Turn a source off because it failed, keeping the reason to show. */
  fail: (key: string, status: Extract<LiveStatus, { state: "refused" | "failed" }>) => void;
  pick: (picked: string | null) => void;
}

export const useLiveStore = create<LiveState>()((set) => ({
  on: {},
  status: {},
  picked: null,
  setOn: (key, on) => set((state) => ({ on: { ...state.on, [key]: on }, status: { ...state.status, [key]: IDLE } })),
  report: (key, status) =>
    set((state) => (sameStatus(state.status[key], status) ? state : { status: { ...state.status, [key]: status } })),
  fail: (key, status) =>
    set((state) => ({ on: { ...state.on, [key]: false }, status: { ...state.status, [key]: status } })),
  pick: (picked) => set({ picked }),
}));

export function liveStatus(status: Readonly<Record<string, LiveStatus>>, key: string): LiveStatus {
  return status[key] ?? IDLE;
}

export function pickedKey(sourceKey: string, recordId: string): string {
  return `${sourceKey}/${recordId}`;
}
