import { useQuery } from "@tanstack/react-query";
import type { GeoJSONSource, LayerSpecification, Map as MapLibreMap } from "maplibre-gl";
import { useEffect, useMemo } from "react";
import { isTransient } from "../../../api/client.js";
import { findView, type Meta } from "../../../api/meta.js";
import { isMapLive } from "../../../map/MapPane.js";
import { useMapStore, useViewAreaStore } from "../../../map/store.js";
import { COLOURS } from "../../../ui/tokens.js";
import { EMPTY_COLLECTION, type FeatureCollection } from "../../records/geojson.js";
import { terrainKeys } from "../keys.js";
import { capturesIn, coverageBox, fetchCoverage, gapsIn, type Ring } from "./coverage.js";
import { type CoverageSummary, IDLE_SUMMARY, useCoverageStore } from "./store.js";

/** Below this zoom coverage isn't asked for: the view holds too many squares to say anything useful. */
export const COVERAGE_MIN_ZOOM = 9;

export const COVERAGE_SOURCES = { tiles: "lidar-coverage", gaps: "lidar-gaps" } as const;
export const COVERAGE_LAYERS = {
  gapsFill: "lidar-gaps-fill",
  gapsLine: "lidar-gaps-line",
  coverageFill: "lidar-coverage-fill",
  coverageLine: "lidar-coverage-line",
} as const;

/** True for a view drawn from the elevation data, where a gap in it means a blank map. */
export function isTerrainView(meta: Meta, id: string | null): boolean {
  return id !== null && findView(meta, id)?.group === "lidar";
}

function polygons(rings: readonly Ring[]): FeatureCollection {
  return {
    type: "FeatureCollection",
    features: rings.map((ring) => ({
      type: "Feature",
      geometry: { type: "Polygon", coordinates: [ring] },
      properties: {},
    })),
  };
}

/**
 * The first layer drawn over the views, so coverage sits on the terrain and
 * under map lines, records and findings. Undefined puts it on top.
 */
function firstOverlayLayer(map: MapLibreMap): string | undefined {
  const layers = map.getStyle().layers;
  let lastView = -1;
  layers.forEach((layer, index) => {
    if (layer.type === "background" || layer.type === "hillshade" || layer.type === "raster") lastView = index;
  });
  return layers[lastView + 1]?.id;
}

const LAYERS: LayerSpecification[] = [
  {
    id: COVERAGE_LAYERS.gapsFill,
    type: "fill",
    source: COVERAGE_SOURCES.gaps,
    paint: { "fill-color": COLOURS.bg, "fill-opacity": 0.72, "fill-antialias": false },
  },
  {
    id: COVERAGE_LAYERS.gapsLine,
    type: "line",
    source: COVERAGE_SOURCES.gaps,
    paint: { "line-color": COLOURS.textMuted, "line-width": 1, "line-opacity": 0.5, "line-dasharray": [2, 3] },
  },
  {
    id: COVERAGE_LAYERS.coverageFill,
    type: "fill",
    source: COVERAGE_SOURCES.tiles,
    paint: { "fill-color": COLOURS.info, "fill-opacity": 0.1, "fill-antialias": false },
  },
  {
    id: COVERAGE_LAYERS.coverageLine,
    type: "line",
    source: COVERAGE_SOURCES.tiles,
    paint: { "line-color": COLOURS.info, "line-width": 1.5, "line-opacity": 0.9 },
  },
];

function ensureLayers(map: MapLibreMap): void {
  if (map.getSource(COVERAGE_SOURCES.gaps)) return;
  map.addSource(COVERAGE_SOURCES.gaps, { type: "geojson", data: EMPTY_COLLECTION });
  map.addSource(COVERAGE_SOURCES.tiles, { type: "geojson", data: EMPTY_COLLECTION });
  const before = firstOverlayLayer(map);
  for (const layer of LAYERS) map.addLayer({ ...layer, layout: { visibility: "none" } }, before);
}

function show(map: MapLibreMap, layers: readonly string[], visible: boolean): void {
  for (const layer of layers) map.setLayoutProperty(layer, "visibility", visible ? "visible" : "none");
}

/**
 * Where one-metre elevation exists, on the map. With the layer panel's
 * coverage switch on, each 5 km tile of data is outlined. Whatever the switch,
 * a pane showing a terrain view shades the squares with no data, so a blank
 * area reads as "nothing here" and not as flat ground. What it finds is
 * summed up in `useCoverageStore` for the panel and the notice on the map.
 */
export function useCoverageOnMap(meta: Meta, main: MapLibreMap | null, compare: MapLibreMap | null): void {
  const visible = useCoverageStore((state) => state.visible);
  const setSummary = useCoverageStore((state) => state.setSummary);
  const mainTerrain = useMapStore((state) => isTerrainView(meta, state.mainView));
  const compareTerrain = useMapStore((state) => isTerrainView(meta, state.compareView));
  const bounds = useViewAreaStore((state) => state.bounds);
  const zoom = useViewAreaStore((state) => state.zoom);

  const wanted = visible || mainTerrain || compareTerrain;
  const close = bounds !== null && zoom >= COVERAGE_MIN_ZOOM;
  const box = close && bounds ? coverageBox(bounds) : null;
  const query = useQuery({
    queryKey: terrainKeys.coverage(box ?? []),
    queryFn: ({ signal }) => {
      if (box === null) throw new Error("Coverage was asked for with no view");
      return fetchCoverage(box, signal);
    },
    enabled: wanted && box !== null,
    // The server caches coverage for a day. It changes only when a nation's data does.
    staleTime: 60 * 60_000,
    retry: (failures, error) => failures < 1 && isTransient(error),
  });

  const tiles = close ? query.data : undefined;
  const gaps = useMemo(() => (tiles && bounds ? gapsIn(bounds, tiles) : null), [tiles, bounds]);

  useEffect(() => {
    let summary: CoverageSummary;
    if (!wanted || bounds === null) summary = IDLE_SUMMARY;
    else if (!close) summary = { ...IDLE_SUMMARY, status: "wide" };
    else if (query.isError) summary = { ...IDLE_SUMMARY, status: "failed" };
    else if (!tiles) summary = { ...IDLE_SUMMARY, status: "loading" };
    else
      summary = {
        status: gaps === null ? "wide" : "ready",
        captures: capturesIn(tiles, bounds),
        gaps: gaps?.rings.length ?? 0,
        cells: gaps?.cells ?? 0,
      };
    setSummary(summary);
  }, [wanted, bounds, close, query.isError, tiles, gaps, setSummary]);

  const tileData = useMemo(() => polygons(tiles?.map((tile) => tile.ring) ?? []), [tiles]);
  const gapData = useMemo(() => polygons(gaps?.rings ?? []), [gaps]);

  useEffect(() => {
    const panes: Array<[MapLibreMap | null, boolean]> = [
      [main, mainTerrain],
      [compare, compareTerrain],
    ];
    for (const [map, terrain] of panes) {
      if (!map || !isMapLive(map)) continue;
      ensureLayers(map);
      (map.getSource(COVERAGE_SOURCES.tiles) as GeoJSONSource | undefined)?.setData(tileData);
      (map.getSource(COVERAGE_SOURCES.gaps) as GeoJSONSource | undefined)?.setData(gapData);
      show(map, [COVERAGE_LAYERS.gapsFill, COVERAGE_LAYERS.gapsLine], terrain);
      show(map, [COVERAGE_LAYERS.coverageFill, COVERAGE_LAYERS.coverageLine], visible);
    }
  }, [main, compare, mainTerrain, compareTerrain, visible, tileData, gapData]);
}
