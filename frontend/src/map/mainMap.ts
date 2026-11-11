import type { Map as MapLibreMap } from "maplibre-gl";
import { create } from "zustand";

/**
 * The main pane's MapLibre map, for features that draw on it or listen to
 * it: marking a finding, choosing a marker. `MapView` publishes it once its
 * style has loaded and withdraws it before the map is removed, so a map read
 * from here is live. A feature that holds one across renders still checks
 * `isMapLive` from `MapPane` before touching it.
 *
 * Features add listeners and DOM of their own and take them away again.
 * They don't change the map's style: that belongs to `MapPane`.
 */
interface MainMapState {
  map: MapLibreMap | null;
  setMap: (map: MapLibreMap | null) => void;
}

export const useMainMapStore = create<MainMapState>()((set) => ({
  map: null,
  setMap: (map) => set({ map }),
}));

/** The main map, or null before it is ready and after it has gone. */
export function useMainMap(): MapLibreMap | null {
  return useMainMapStore((state) => state.map);
}
