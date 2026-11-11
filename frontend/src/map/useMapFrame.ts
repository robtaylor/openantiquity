import type { Map as MapLibreMap } from "maplibre-gl";
import { useEffect, useState } from "react";
import { isMapLive } from "./MapPane.js";

/**
 * A number that changes each time `map` is drawn somewhere new: on every
 * frame of a move and on a resize, at most once per animation frame. A
 * component that places things over the map with `map.project` reads it,
 * so it re-renders as the map moves and nothing else does.
 */
export function useMapFrame(map: MapLibreMap | null): number {
  const [frame, setFrame] = useState(0);
  useEffect(() => {
    if (!map || !isMapLive(map)) return;
    let scheduled: number | null = null;
    const onMove = (): void => {
      if (scheduled !== null) return;
      scheduled = requestAnimationFrame(() => {
        scheduled = null;
        setFrame((n) => n + 1);
      });
    };
    map.on("move", onMove);
    map.on("resize", onMove);
    setFrame((n) => n + 1);
    return () => {
      if (scheduled !== null) cancelAnimationFrame(scheduled);
      map.off("move", onMove);
      map.off("resize", onMove);
    };
  }, [map]);
  return frame;
}

/** The place under a point on the screen, given in client pixels. */
export function lngLatAtClient(map: MapLibreMap, clientX: number, clientY: number): [number, number] {
  const box = map.getContainer().getBoundingClientRect();
  const { lng, lat } = map.unproject([clientX - box.left, clientY - box.top]);
  return [lng, lat];
}

/** Where a place is on the screen, in pixels from the top left of the map. */
export function screenPoint(map: MapLibreMap, [lng, lat]: [number, number]): { x: number; y: number } {
  const { x, y } = map.project([lng, lat]);
  return { x, y };
}
