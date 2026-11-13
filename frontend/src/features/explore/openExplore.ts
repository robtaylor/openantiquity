import { useCallback } from "react";
import { useNavigate } from "react-router";
import { useMapStore } from "../../map/store.js";

/**
 * Open Explore with the map at a place, at least `minZoom` close, so the
 * findings there can be told apart in its list: for a square holding
 * several findings, or "Show all in Explore" from the chooser.
 */
export function useOpenExploreAt(): (lngLat: readonly [number, number], minZoom: number) => void {
  const navigate = useNavigate();
  return useCallback(
    ([lng, lat], minZoom) => {
      const { camera, requestCamera } = useMapStore.getState();
      requestCamera({ lng, lat, zoom: Math.max(camera.zoom, minZoom) });
      navigate("/");
    },
    [navigate],
  );
}
