import { keepPreviousData, useQuery } from "@tanstack/react-query";
import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
import { useEffect, useMemo, useRef } from "react";
import { create } from "zustand";
import { isTransient } from "../../api/client.js";
import { findOverlay, type Meta } from "../../api/meta.js";
import { isMapLive } from "../../map/MapPane.js";
import { useMapStore, useViewAreaStore } from "../../map/store.js";
import { overlayShown, overlaySourceId } from "../../map/style.js";
import { overlayTroubleKey } from "../../map/trouble.js";
import { COLOURS } from "../../ui/tokens.js";
import { EMPTY_COLLECTION } from "../records/geojson.js";
import { fetchScanCoverage, type Square } from "./api.js";
import { scanKeys } from "./keys.js";
import { coverageBox, coverageFeatures, squareFeatures } from "./square.js";

// --------------------------------------------------------------------------
// The square being scanned
// --------------------------------------------------------------------------

/** The square drawn on the map: set by `ScanLayer` while a scan is on screen, or while a finding is marked in it. */
interface ScanSquareOnMap {
  square: Square | null;
  setSquare: (square: Square | null) => void;
}

export const useScanSquareOnMap = create<ScanSquareOnMap>()((set, get) => ({
  square: null,
  setSquare: (square) => {
    if (get().square !== square) set({ square });
  },
}));

export const SQUARE_SOURCES = { outline: "scan-square", shade: "scan-shade" } as const;
export const SQUARE_LAYERS = { shade: "scan-shade-fill", outline: "scan-square-line" } as const;
/** How dark the ground outside the square is: a little, so the eye stays in but the context still reads. */
export const SHADE_OPACITY = 0.38;

/** The findings' markers stay above the shade and the outline, so a finding just outside still shows and takes its clicks. */
function firstFindingsLayer(map: MapLibreMap): string | undefined {
  return map.getStyle().layers?.find((layer) => layer.id.startsWith("findings"))?.id;
}

function ensureSquareLayers(map: MapLibreMap): void {
  if (map.getSource(SQUARE_SOURCES.outline)) return;
  map.addSource(SQUARE_SOURCES.shade, { type: "geojson", data: EMPTY_COLLECTION });
  map.addSource(SQUARE_SOURCES.outline, { type: "geojson", data: EMPTY_COLLECTION });
  const before = firstFindingsLayer(map);
  map.addLayer(
    {
      id: SQUARE_LAYERS.shade,
      type: "fill",
      source: SQUARE_SOURCES.shade,
      paint: { "fill-color": COLOURS.bg, "fill-opacity": SHADE_OPACITY, "fill-antialias": false },
    },
    before,
  );
  map.addLayer(
    {
      id: SQUARE_LAYERS.outline,
      type: "line",
      source: SQUARE_SOURCES.outline,
      layout: { "line-join": "miter" },
      paint: { "line-color": COLOURS.accentStrong, "line-width": 2 },
    },
    before,
  );
}

function useSquareOnMap(main: MapLibreMap | null, compare: MapLibreMap | null): void {
  const square = useScanSquareOnMap((state) => state.square);
  const features = useMemo(() => squareFeatures(square), [square]);
  useEffect(() => {
    for (const map of [main, compare]) {
      if (!map || !isMapLive(map)) continue;
      // Nothing is added to a map until there is a square to draw.
      if (!square && !map.getSource(SQUARE_SOURCES.outline)) continue;
      ensureSquareLayers(map);
      (map.getSource(SQUARE_SOURCES.shade) as GeoJSONSource | undefined)?.setData(features.shade);
      (map.getSource(SQUARE_SOURCES.outline) as GeoJSONSource | undefined)?.setData(features.outline);
    }
  }, [main, compare, square, features]);
}

// --------------------------------------------------------------------------
// Coverage
// --------------------------------------------------------------------------

/**
 * What the coverage layer can say about the view, for the layer panel and
 * the scan panel. "off": the layer is off. "wide": zoomed out too far to
 * ask. "loading", "ready" and "failed" follow the request, and `scanned` is
 * how many squares in the box asked about someone has scanned.
 */
export interface ScanCoverageSummary {
  status: "off" | "wide" | "loading" | "ready" | "failed";
  scanned: number;
}

interface ScanCoverageState {
  summary: ScanCoverageSummary;
  setSummary: (summary: ScanCoverageSummary) => void;
}

const OFF: ScanCoverageSummary = { status: "off", scanned: 0 };

export const useScanCoverage = create<ScanCoverageState>()((set, get) => ({
  summary: OFF,
  setSummary: (summary) => {
    const current = get().summary;
    if (current.status !== summary.status || current.scanned !== summary.scanned) set({ summary });
  },
}));

/** Coverage changes as people scan, and the server lets it be cached for five minutes. */
const COVERAGE_STALE_MS = 5 * 60_000;

function useCoverageOnMap(meta: Meta, main: MapLibreMap | null, compare: MapLibreMap | null): void {
  const overlayId = findOverlay(meta, "coverage")?.id;
  const key = overlayId === undefined ? null : overlayTroubleKey(overlayId);
  const shown = useMapStore((state) => overlayId !== undefined && overlayShown(state, overlayId));
  const attempt = useMapStore((state) => (key === null ? 0 : (state.retries[key] ?? 0)));
  const bounds = useViewAreaStore((state) => state.bounds);
  const box = useMemo(() => (bounds ? coverageBox(bounds) : null), [bounds]);

  const query = useQuery({
    queryKey: scanKeys.coverage(box ?? [], attempt),
    queryFn: ({ signal }) => {
      if (box === null) throw new Error("Coverage was asked for with no box");
      return fetchScanCoverage(box, signal);
    },
    enabled: shown && box !== null,
    staleTime: COVERAGE_STALE_MS,
    placeholderData: keepPreviousData,
    retry: (failures, error) => failures < 1 && isTransient(error),
  });

  // A failure turns the layer off with the layer panel's notice and "Try again", as a failing tile source does.
  const handled = useRef(0);
  useEffect(() => {
    if (key === null || query.errorUpdatedAt <= handled.current) return;
    handled.current = query.errorUpdatedAt;
    console.warn(`[map] Scan coverage could not be loaded: ${query.error?.message ?? "unknown error"}`);
    useMapStore.getState().setSourceFailing(key, true);
  }, [key, query.error, query.errorUpdatedAt]);

  const shownData = shown && box !== null ? query.data : undefined;
  const data = useMemo(() => (shownData ? coverageFeatures(shownData) : EMPTY_COLLECTION), [shownData]);

  useEffect(() => {
    let summary: ScanCoverageSummary;
    if (!shown) summary = OFF;
    else if (bounds === null || box === null) summary = { status: "wide", scanned: 0 };
    else if (query.isError) summary = { status: "failed", scanned: 0 };
    else if (!query.data || query.isPlaceholderData) summary = { status: "loading", scanned: 0 };
    else summary = { status: "ready", scanned: query.data.features?.length ?? 0 };
    useScanCoverage.getState().setSummary(summary);
  }, [shown, bounds, box, query.isError, query.data, query.isPlaceholderData]);

  useEffect(() => {
    if (overlayId === undefined) return;
    const source = overlaySourceId(overlayId);
    for (const map of [main, compare]) {
      if (!map || !isMapLive(map)) continue;
      (map.getSource(source) as GeoJSONSource | undefined)?.setData(data);
    }
  }, [main, compare, overlayId, data]);
}

/**
 * What "Scan a square" draws on both panes: the square being scanned,
 * outlined, with the ground outside it shaded a little; and the scan
 * coverage overlay's squares, from `GET /squares/coverage`, while that
 * overlay is on and the view is small enough to ask about.
 */
export function useScanOnMap(meta: Meta, main: MapLibreMap | null, compare: MapLibreMap | null): void {
  useSquareOnMap(main, compare);
  useCoverageOnMap(meta, main, compare);
}
