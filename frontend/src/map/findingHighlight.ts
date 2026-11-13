/**
 * The finding the map highlights while something points at it without
 * opening it: an entry of the chooser that is hovered or focused, what a
 * click would open as the pointer moves on a computer, or a row of the
 * Explore list that has focus (Decision 0031). The findings overlay has a
 * highlight layer for markers and one for lines and area edges, whose
 * filters name the finding, so the highlight hides with the overlay.
 */

import type { Map as MapLibreMap } from "maplibre-gl";
import { useEffect } from "react";
import { create } from "zustand";
import { isMapLive } from "./MapPane.js";
import { FINDING_HIGHLIGHT_LAYERS, highlightFilters } from "./overlayLayers.js";

interface HighlightState {
  publicId: string | null;
  set: (publicId: string | null) => void;
  /** Take the highlight off, if it is still on `publicId`. */
  clear: (publicId: string) => void;
}

export const useFindingHighlight = create<HighlightState>()((set, get) => ({
  publicId: null,
  set: (publicId) => set({ publicId }),
  clear: (publicId) => {
    if (get().publicId === publicId) set({ publicId: null });
  },
}));

/** Keep the main map's highlight layers on the highlighted finding. */
export function useFindingHighlightOnMap(map: MapLibreMap | null): void {
  const publicId = useFindingHighlight((state) => state.publicId);
  useEffect(() => {
    if (!map || !isMapLive(map)) return;
    const filters = highlightFilters(publicId);
    for (const role of ["shape", "marker"] as const) {
      const layer = FINDING_HIGHLIGHT_LAYERS[role];
      if (map.getLayer(layer)) map.setFilter(layer, filters[role]);
    }
  }, [map, publicId]);
}
