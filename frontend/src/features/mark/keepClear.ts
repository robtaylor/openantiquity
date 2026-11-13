/**
 * Keeping the points already placed clear of the phone's drawing bar at the
 * foot of the map. Whenever the bar appears or changes size the map moves up
 * by as little as clears them. Points beside the bar, or below it, are left
 * alone. The drawing guide at the top never moves the map.
 */

import type { Map as MapLibreMap } from "maplibre-gl";
import { screenPoint } from "../../map/useMapFrame.js";
import { useMarkStore } from "./markStore.js";

/** Half a handle's dot, in pixels. */
export const DOT_RADIUS_PX = 6;
/** Room kept between a point's dot and the bar's top, in pixels. */
export const BAR_CLEARANCE_PX = 8;

export interface Box {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

interface Place {
  x: number;
  y: number;
}

function beside(place: Place, box: Box): boolean {
  return place.x + DOT_RADIUS_PX < box.left || place.x - DOT_RADIUS_PX > box.right;
}

/** How far up the map must move, in pixels, for no point to be under the bar or just above it. */
export function liftOverBar(places: readonly Place[], bar: Box): number {
  let lowest: number | null = null;
  for (const place of places) {
    const clear = place.y + DOT_RADIUS_PX < bar.top - BAR_CLEARANCE_PX || place.y - DOT_RADIUS_PX > bar.bottom;
    if (beside(place, bar) || clear) continue;
    lowest = lowest === null ? place.y : Math.max(lowest, place.y);
  }
  return lowest === null ? 0 : lowest + DOT_RADIUS_PX + BAR_CLEARANCE_PX - bar.top;
}

/** Every point placed, on the page. */
function placesOnPage(map: MapLibreMap): Place[] {
  const frame = map.getContainer().getBoundingClientRect();
  return useMarkStore.getState().shape.present.points.map((point) => {
    const at = screenPoint(map, [point.lon, point.lat]);
    return { x: frame.left + at.x, y: frame.top + at.y };
  });
}

/** Move the map up by as little as clears every point from under the phone's bar. */
export function clearPointsOfBar(map: MapLibreMap, bar: DOMRect): void {
  if (bar.height === 0) return;
  const up = liftOverBar(placesOnPage(map), bar);
  if (up > 0) map.panBy([0, up], { duration: 0 });
}
