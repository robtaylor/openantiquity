import type { Map as MapLibreMap, MapMouseEvent } from "maplibre-gl";
import { FINDING_POINT_LAYERS } from "./overlayLayers.js";

const POINT_LAYERS: readonly string[] = Object.values(FINDING_POINT_LAYERS);

/**
 * The finding drawn at an exact position under a click or tap, if there is
 * one. Findings sit above heritage records, so the records feature asks this
 * first and leaves such a click to Explore.
 */
export function findingPointAt(
  map: MapLibreMap,
  event: MapMouseEvent,
): { publicId: string; at: [number, number] } | null {
  const layers = POINT_LAYERS.filter((id) => map.getLayer(id) !== undefined);
  if (layers.length === 0) return null;
  for (const feature of map.queryRenderedFeatures(event.point, { layers })) {
    const publicId = feature.properties?.public_id;
    const geometry = feature.geometry;
    if (typeof publicId !== "string") continue;
    const at: [number, number] =
      geometry?.type === "Point" && Array.isArray(geometry.coordinates)
        ? [Number(geometry.coordinates[0]), Number(geometry.coordinates[1])]
        : [event.lngLat.lng, event.lngLat.lat];
    return { publicId, at };
  }
  return null;
}
