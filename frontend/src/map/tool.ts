import { create } from "zustand";

/**
 * Which tool, if any, has taken over clicks on the map, such as the height
 * profile's line. While one has, features on the map don't open on a click,
 * so placing a point on a record doesn't open the record.
 */
export interface MapToolState {
  tool: string | null;
  setTool: (tool: string | null) => void;
}

export const useMapTool = create<MapToolState>()((set) => ({
  tool: null,
  setTool: (tool) => set({ tool }),
}));

/** True while a tool has taken over clicks. For map click handlers to check first. */
export function mapToolActive(): boolean {
  return useMapTool.getState().tool !== null;
}
