import type { MouseEvent } from "react";
import { useNavigate } from "react-router";
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

/** Enough of a finding to open its page and mark it: its id and the position this viewer may see. */
export interface FindingToOpen {
  public_id: string;
  location: { lon: number; lat: number; obscured: boolean };
}

/**
 * A click handler for a link to a finding's page: it marks the finding on the
 * map, as its square when obscured, and opens the page through the router. A
 * click with a modifier key, or not with the main button, is left to the browser.
 */
export function useOpenFinding(): (finding: FindingToOpen) => (event: MouseEvent<HTMLAnchorElement>) => void {
  const navigate = useNavigate();
  const select = useSelectedFinding((state) => state.select);
  return ({ public_id: publicId, location }) =>
    (event) => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
      event.preventDefault();
      select(publicId, [location.lon, location.lat], location.obscured);
      navigate(findingPath(publicId));
    };
}
