import { create } from "zustand";
import { kmSquareAt } from "../../map/gridref.js";
import { onPersonChanged } from "../account/session.js";

/**
 * The finding last chosen from the list or the map, so the map can mark it
 * while its page is open. An obscured finding is marked by its one-kilometre
 * square, never by a point (Decision 0005). What one viewer may see isn't
 * what the next may, so it is cleared when the person changes, and the page
 * marks the finding again from what the server tells the new viewer.
 */
export interface SelectedFinding {
  publicId: string;
  /** The position this viewer may see: the finding itself, or the centre of its square. */
  point: [number, number];
  /** The square's corners when the position is obscured, otherwise null. */
  square: Array<[number, number]> | null;
}

interface SelectionState {
  selected: SelectedFinding | null;
  select: (publicId: string, point: [number, number], obscured: boolean) => void;
  clear: () => void;
}

export const useSelectedFinding = create<SelectionState>()((set) => ({
  selected: null,
  select: (publicId, point, obscured) =>
    set({ selected: { publicId, point, square: obscured ? (kmSquareAt(point[0], point[1])?.ring ?? null) : null } }),
  clear: () => set({ selected: null }),
}));

onPersonChanged(() => useSelectedFinding.getState().clear());

/** The path of a finding's page. */
export function findingPath(publicId: string): string {
  return `/f/${encodeURIComponent(publicId)}`;
}
