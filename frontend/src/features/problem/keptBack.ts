/**
 * Whether the page someone is on shows a place that is kept back from them,
 * so a problem report may not offer to add where the map is.
 *
 * The answer comes from the server, never from the page's own reckoning: a
 * finding's `location.obscured`, and an investigation's `places_kept_back`,
 * which its guard sets (`sensitivity.PositionGuard`, Decision 0005). A page
 * that shows a finding says what it was told with `useKeepsPlaceBack`, and
 * until it has been told anything, or on such a page whose panel isn't
 * open, the place counts as kept back.
 */

import { useEffect } from "react";
import { useLocation } from "react-router";
import { create } from "zustand";
import { onPersonChanged } from "../account/session.js";
import { pagePattern } from "./report.js";

/** The pages, by their patterns in `report.ts`, that show one finding or an investigation that may hold one. */
const PAGES_WITH_A_FINDING = new Set(["/f/:id", "/mark/finding/:publicId", "/i/:id", "/review"]);

interface KeptBackState {
  /** What each page last said, by its path. */
  said: Record<string, boolean>;
  say: (path: string, keptBack: boolean) => void;
  forget: () => void;
}

const useKeptBackStore = create<KeptBackState>()((set) => ({
  said: {},
  say: (path, keptBack) =>
    set((state) => (state.said[path] === keptBack ? state : { said: { ...state.said, [path]: keptBack } })),
  forget: () => set({ said: {} }),
}));

// What one viewer is kept from isn't what the next is.
onPersonChanged(() => useKeptBackStore.getState().forget());

/**
 * Say whether this page shows a place kept back from the person: the
 * server's answer, or undefined while it hasn't come, which counts as yes.
 */
export function useKeepsPlaceBack(keptBack: boolean | undefined): void {
  const { pathname } = useLocation();
  const say = useKeptBackStore((state) => state.say);
  useEffect(() => {
    say(pathname, keptBack !== false);
  }, [pathname, keptBack, say]);
}

function keptBackAt(said: Record<string, boolean>, pathname: string): boolean {
  if (!PAGES_WITH_A_FINDING.has(pagePattern(pathname))) return false;
  return said[pathname] !== false;
}

/** Whether a report made at `pathname` must leave out where the map is. Kept current. */
export function usePlaceKeptBack(pathname: string): boolean {
  return useKeptBackStore((state) => keptBackAt(state.said, pathname));
}
