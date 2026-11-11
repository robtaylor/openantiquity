import { create } from "zustand";

/**
 * The sample under the pointer, shared by the chart and the line on the map.
 * Either one sets it and both draw it. The line itself lives in the address,
 * and its heights in the query cache.
 */
export interface ProfileHoverState {
  /** Index into the profile's samples, or null when the pointer is on neither. */
  hover: number | null;
  setHover: (hover: number | null) => void;
}

export const useProfileHover = create<ProfileHoverState>()((set, get) => ({
  hover: null,
  setHover: (hover) => {
    if (get().hover !== hover) set({ hover });
  },
}));
