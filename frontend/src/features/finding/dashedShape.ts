/**
 * A shape that isn't the finding's own, drawn on the map for someone to
 * weigh against it: a suggested change (`SuggestedChanges`) or an earlier
 * shape an admin may put back (`RemoveMarkingPanel`). It is a wide band,
 * dashed light over a dark edge, drawn beneath every finding's own line.
 * Where the two run together the finding's line shows solid down the
 * middle with the dashes on either side of it. Where they part each shows
 * alone, so what the shape would gain and what it would lose are both in
 * sight, on pale ground and dark.
 */

import type { Map as MapLibreMap } from "maplibre-gl";
import { useMemo } from "react";
import { FINDING_SHAPE_LAYERS } from "../../map/overlayLayers.js";
import { COLOURS } from "../../ui/tokens.js";
import type { GeoJSONGeometry } from "../findings/types.js";
import { useSourceData } from "../mark/MarkLayer.js";
import { EMPTY_COLLECTION, type FeatureCollection } from "../records/geojson.js";

export interface DashedLayers {
  fill: string;
  casing: string;
  line: string;
}

/** The ids of the three layers drawn from the source `prefix`. */
export function dashedLayers(prefix: string): DashedLayers {
  return { fill: `${prefix}-fill`, casing: `${prefix}-casing`, line: `${prefix}-line` };
}

/** Draw `geometry` from the map's source `source`, and nothing once it is null or the caller goes. */
export function useDashedShapeOnMap(
  map: MapLibreMap | null,
  source: string,
  layers: DashedLayers,
  geometry: GeoJSONGeometry | null,
): void {
  const data = useMemo<FeatureCollection>(
    () =>
      geometry
        ? ({
            type: "FeatureCollection",
            features: [{ type: "Feature", geometry, properties: {} }],
          } as FeatureCollection)
        : EMPTY_COLLECTION,
    [geometry],
  );
  const addLayers = useMemo(
    () => (target: MapLibreMap) => {
      // Beneath the findings' own shapes, which start with the areas' fills.
      const before = target.getLayer(FINDING_SHAPE_LAYERS.areaFills) ? FINDING_SHAPE_LAYERS.areaFills : undefined;
      target.addLayer(
        {
          id: layers.fill,
          type: "fill",
          source,
          filter: ["==", ["geometry-type"], "Polygon"],
          paint: { "fill-color": COLOURS.text, "fill-opacity": 0.08 },
        },
        before,
      );
      target.addLayer(
        {
          id: layers.casing,
          type: "line",
          source,
          layout: { "line-join": "round", "line-cap": "round" },
          paint: { "line-color": COLOURS.bg, "line-width": 14, "line-opacity": 0.85 },
        },
        before,
      );
      target.addLayer(
        {
          id: layers.line,
          type: "line",
          source,
          layout: { "line-join": "round" },
          paint: { "line-color": COLOURS.text, "line-width": 10, "line-dasharray": [1, 0.8] },
        },
        before,
      );
    },
    [source, layers.fill, layers.casing, layers.line],
  );
  useSourceData(map, source, data, addLayers, true);
}
