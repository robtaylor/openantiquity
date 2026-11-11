import { useEffect } from "react";
import { create } from "zustand";

/**
 * Reasons the findings overlay is held back, whatever the person's own
 * choice in the layer panel. A blind second look is one: a marker at the
 * spot says someone has marked something there, and its title says what
 * (Decision 0008). While any reason is held, the overlay asks the server for
 * nothing and draws nothing, and the person's switch is left as it was.
 */
interface HiddenFindingsState {
  reasons: readonly string[];
  hide: (reason: string) => void;
  show: (reason: string) => void;
}

export const useHiddenFindings = create<HiddenFindingsState>()((set) => ({
  reasons: [],
  hide: (reason) => set((state) => (state.reasons.includes(reason) ? state : { reasons: [...state.reasons, reason] })),
  show: (reason) =>
    set((state) => (state.reasons.includes(reason) ? { reasons: state.reasons.filter((r) => r !== reason) } : state)),
}));

/** True while some feature holds the findings overlay back. */
export function useFindingsHidden(): boolean {
  return useHiddenFindings((state) => state.reasons.length > 0);
}

/** Hold the findings overlay back for `reason` while `active` is true. */
export function useHideFindingsWhile(reason: string, active: boolean): void {
  useEffect(() => {
    if (!active) return;
    useHiddenFindings.getState().hide(reason);
    return () => useHiddenFindings.getState().show(reason);
  }, [reason, active]);
}
