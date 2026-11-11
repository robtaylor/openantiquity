import { create } from "zustand";

/**
 * Where marking a finding goes back to, set by a mode that opened marking
 * over itself, such as a scan. With one set, saving the finding, keeping it
 * as a draft or closing the panel goes back there, so the mode carries on.
 * Null, the usual case, leaves marking to end as it always has: a saved
 * finding opens its page, and closing goes to the bare map.
 */
export interface MarkReturn {
  path: string;
  /** What the way back is called, such as "Back to the square". */
  label: string;
}

interface MarkReturnState {
  to: MarkReturn | null;
  set: (to: MarkReturn | null) => void;
}

export const useMarkReturn = create<MarkReturnState>()((set) => ({
  to: null,
  set: (to) => set({ to }),
}));
