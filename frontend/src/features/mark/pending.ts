import { create } from "zustand";
import type { LngLat } from "./path.js";

/**
 * Findings being saved right now, drawn on the map and listed in Explore at
 * once (docs/UI.md: saves are optimistic). Each goes when its save fails, or
 * once the findings in view have been asked for again and include it.
 */
export interface PendingFinding {
  id: number;
  point: LngLat;
  title: string;
  featureClass: string;
}

interface PendingState {
  pending: readonly PendingFinding[];
  add: (finding: Omit<PendingFinding, "id">) => number;
  remove: (id: number) => void;
}

let nextId = 1;

export const usePendingFindings = create<PendingState>()((set) => ({
  pending: [],
  add: (finding) => {
    const id = nextId++;
    set((state) => ({ pending: [...state.pending, { ...finding, id }] }));
    return id;
  },
  remove: (id) => set((state) => ({ pending: state.pending.filter((finding) => finding.id !== id) })),
}));
