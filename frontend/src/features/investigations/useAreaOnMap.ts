import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
import { useEffect, useMemo } from "react";
import { isMapLive } from "../../map/MapPane.js";
import { COLOURS } from "../../ui/tokens.js";
import { EMPTY_COLLECTION, type FeatureCollection } from "../records/geojson.js";
import { type AreaShape, useInvestigationArea } from "./area.js";

export const AREA_SOURCE = "investigation-area";
export const AREA_LAYERS = { fill: "investigation-area-fill", line: "investigation-area-line" } as const;

/** The area as map features: one polygon per polygon of the area, with its holes, which the fill and the line both read. */
export function areaFeatures(shape: AreaShape | null): FeatureCollection {
  if (!shape) return EMPTY_COLLECTION;
  return {
    type: "FeatureCollection",
    features: shape.polygons.map((rings) => ({
      type: "Feature",
      geometry: { type: "Polygon", coordinates: rings.map((ring) => ring.map((point) => [...point])) },
      properties: {},
    })),
  };
}

/** The findings' markers stay above the area, so it never hides one or takes its clicks. */
function firstFindingsLayer(map: MapLibreMap): string | undefined {
  return map.getStyle().layers?.find((layer) => layer.id.startsWith("findings"))?.id;
}

function ensureLayers(map: MapLibreMap): void {
  if (map.getSource(AREA_SOURCE)) return;
  map.addSource(AREA_SOURCE, { type: "geojson", data: EMPTY_COLLECTION });
  const before = firstFindingsLayer(map);
  map.addLayer(
    {
      id: AREA_LAYERS.fill,
      type: "fill",
      source: AREA_SOURCE,
      paint: { "fill-color": COLOURS.accent, "fill-opacity": 0.06 },
    },
    before,
  );
  map.addLayer(
    {
      id: AREA_LAYERS.line,
      type: "line",
      source: AREA_SOURCE,
      layout: { "line-join": "round" },
      paint: { "line-color": COLOURS.accent, "line-width": 2, "line-dasharray": [3, 2] },
    },
    before,
  );
}

/**
 * The open investigation's area, drawn on both panes as a dashed ochre
 * outline over the faintest fill, under the findings, so the terrain inside
 * stays in sight.
 */
export function useAreaOnMap(main: MapLibreMap | null, compare: MapLibreMap | null): void {
  const shape = useInvestigationArea((state) => state.shape);
  const data = useMemo(() => areaFeatures(shape), [shape]);
  useEffect(() => {
    for (const map of [main, compare]) {
      if (!map || !isMapLive(map)) continue;
      // Nothing is added to a map until there is an area to draw.
      if (!shape && !map.getSource(AREA_SOURCE)) continue;
      ensureLayers(map);
      (map.getSource(AREA_SOURCE) as GeoJSONSource | undefined)?.setData(data);
    }
  }, [main, compare, shape, data]);
}
