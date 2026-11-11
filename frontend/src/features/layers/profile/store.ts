import { create } from "zustand";
import type { LngLat } from "./line.js";

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

/**
 * Finds the ground under the cross that "Add a point at the cross" uses. Set
 * by the map while the profile is open, since only the map can turn a spot
 * on screen into a position; null while there is no map to ask.
 */
export interface ProfileCrossState {
  locate: (() => LngLat | null) | null;
  setLocate: (locate: (() => LngLat | null) | null) => void;
}

export const useProfileCross = create<ProfileCrossState>()((set) => ({
  locate: null,
  setLocate: (locate) => set({ locate }),
}));
