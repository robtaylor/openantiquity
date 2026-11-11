import type { GeoJSONSource, MapGeoJSONFeature, Map as MapLibreMap, MapMouseEvent, PointLike } from "maplibre-gl";
import { useEffect, useMemo, useRef } from "react";
import { useLocation, useNavigate } from "react-router";
import { findOverlay, type Meta } from "../../api/meta.js";
import { isMapLive } from "../../map/MapPane.js";
import { RECORD_LAYERS, recordsLiveSourceId, recordsSelectionSourceId } from "../../map/overlayLayers.js";
import { useMapStore } from "../../map/store.js";
import { overlayShown, overlaySourceId } from "../../map/style.js";
import { mapToolActive } from "../../map/tool.js";
import { FILTERED_RECORD_LAYERS, recordLayerFilter, useRecordFilters } from "./filters.js";
import { EMPTY_COLLECTION, type FeatureCollection } from "./geojson.js";
import { pickedKey, useLiveStore } from "./live/store.js";
import { useLiveRecords } from "./live/useLiveRecords.js";
import { useRecordsOnScreen } from "./onScreen.js";
import { elsewherePath, recordPath } from "./paths.js";
import { useRecordSelection } from "./shape.js";

/** The layers a click or a hover can land on, top first. */
const CLICKABLE = [
  RECORD_LAYERS.live,
  RECORD_LAYERS.liveCentres,
  RECORD_LAYERS.squares,
  RECORD_LAYERS.outlines,
  RECORD_LAYERS.counts,
  RECORD_LAYERS.countLabels,
];
/** The layers whose features say which stored sources are on screen. */
const CREDITED = [RECORD_LAYERS.squares, RECORD_LAYERS.outlines, RECORD_LAYERS.counts];
/** A count is zoomed into by this many levels when clicked. */
const COUNT_ZOOM_STEP = 2;

export type RecordTarget =
  | { kind: "record"; id: number }
  | { kind: "count"; lng: number; lat: number }
  | { kind: "live"; source: string; id: string };

type Hit = Pick<MapGeoJSONFeature, "id" | "properties"> & { layer: { id: string } };

/** What a click on these features, topmost first, should open. */
export function recordTarget(hits: readonly Hit[], at: { lng: number; lat: number }): RecordTarget | null {
  for (const hit of hits) {
    const props = hit.properties ?? {};
    const layer = hit.layer.id;
    if (layer === RECORD_LAYERS.live || layer === RECORD_LAYERS.liveCentres) {
      if (typeof props.source === "string" && typeof props.id === "string") {
        return { kind: "live", source: props.source, id: props.id };
      }
    } else if (layer === RECORD_LAYERS.squares || layer === RECORD_LAYERS.outlines) {
      const id = Number(props.id ?? hit.id);
      if (Number.isSafeInteger(id) && id > 0) return { kind: "record", id };
    } else if (layer === RECORD_LAYERS.counts || layer === RECORD_LAYERS.countLabels) {
      return { kind: "count", ...at };
    }
  }
  return null;
}

/** The stored sources named by these features: a record's `source`, or a count's comma-separated `sources`. */
export function sourcesOf(features: ReadonlyArray<Pick<MapGeoJSONFeature, "properties">>): string[] {
  const keys = new Set<string>();
  for (const feature of features) {
    const props = feature.properties ?? {};
    if (typeof props.source === "string") keys.add(props.source);
    if (typeof props.sources === "string") for (const key of props.sources.split(",")) if (key) keys.add(key);
  }
  return [...keys];
}

function existing(map: MapLibreMap, layers: readonly string[]): string[] {
  return layers.filter((layer) => map.getLayer(layer) !== undefined);
}

function query(map: MapLibreMap, layers: readonly string[], point?: PointLike): Hit[] {
  const present = existing(map, layers);
  if (present.length === 0) return [];
  const options = { layers: present };
  return (
    point === undefined ? map.queryRenderedFeatures(options) : map.queryRenderedFeatures(point, options)
  ) as Hit[];
}

function setData(map: MapLibreMap, sourceId: string, data: FeatureCollection): void {
  (map.getSource(sourceId) as GeoJSONSource | undefined)?.setData(data);
}

/**
 * Heritage records on the map, beyond what the style draws by itself: the
 * category and source filters from the layer panel, what the live sources
 * sent, the outline of the open record, and what clicks do. A record opens
 * its page, a count zooms in, and a live record is shown in the layer
 * panel, since it has no page here. A right click, or a long press where the
 * browser gives one, opens the links to other viewers for that spot. When
 * the main map comes to rest it reports which stored sources it is showing,
 * so the credits name exactly those.
 */
export function useRecordsOnMap(meta: Meta, main: MapLibreMap | null, compare: MapLibreMap | null): void {
  const overlay = findOverlay(meta, "records");
  const shown = useMapStore((state) => overlay !== undefined && overlayShown(state, overlay.id));
  const live = useLiveRecords(shown);
  const selection = useRecordSelection((state) => state.shape);
  const hiddenCategories = useRecordFilters((state) => state.hiddenCategories);
  const hiddenSources = useRecordFilters((state) => state.hiddenSources);
  const knownSources = useMemo(() => meta.sources.map((source) => source.key), [meta]);

  const navigate = useNavigate();
  const location = useLocation();
  const latest = useRef({ navigate, pathname: location.pathname });
  latest.current = { navigate, pathname: location.pathname };

  const source = overlay ? overlaySourceId(overlay.id) : null;

  useEffect(() => {
    for (const map of [main, compare]) {
      if (!map || !isMapLive(map)) continue;
      for (const layer of existing(map, FILTERED_RECORD_LAYERS)) {
        map.setFilter(layer, recordLayerFilter(layer, hiddenCategories, hiddenSources, knownSources));
      }
    }
  }, [main, compare, hiddenCategories, hiddenSources, knownSources]);

  useEffect(() => {
    if (source === null) return;
    for (const map of [main, compare]) if (map && isMapLive(map)) setData(map, recordsLiveSourceId(source), live);
  }, [main, compare, source, live]);

  useEffect(() => {
    if (source === null) return;
    const shape = selection ?? EMPTY_COLLECTION;
    for (const map of [main, compare]) if (map && isMapLive(map)) setData(map, recordsSelectionSourceId(source), shape);
  }, [main, compare, source, selection]);

  useEffect(() => {
    const maps = [main, compare].filter((map): map is MapLibreMap => map !== null && isMapLive(map));
    const detach: Array<() => void> = [];
    for (const map of maps) {
      const onClick = (event: MapMouseEvent): void => {
        // A tool such as the height profile has the clicks while it is open.
        if (!isMapLive(map) || mapToolActive()) return;
        const target = recordTarget(query(map, CLICKABLE, event.point), event.lngLat);
        if (target === null) return;
        const { navigate: go, pathname } = latest.current;
        if (target.kind === "record") go(recordPath(target.id));
        else if (target.kind === "count") {
          const zoom = useMapStore.getState().camera.zoom + COUNT_ZOOM_STEP;
          useMapStore.getState().requestCamera({ lng: target.lng, lat: target.lat, zoom });
        } else {
          useLiveStore.getState().pick(pickedKey(target.source, target.id));
          go({ pathname, search: "?panel=layers" });
        }
      };
      // The pointer is checked at most once a frame, however often it moves.
      let pending: MapMouseEvent | null = null;
      let frame = 0;
      const onMove = (event: MapMouseEvent): void => {
        // A drag moves the map, not the pointer over it, so there is nothing to check.
        // A tool that has the clicks sets its own cursor.
        if (event.originalEvent?.buttons || mapToolActive()) return;
        pending = event;
        if (frame !== 0) return;
        frame = requestAnimationFrame(() => {
          frame = 0;
          if (!pending || !isMapLive(map)) return;
          const over = query(map, CLICKABLE, pending.point).length > 0;
          map.getCanvas().style.cursor = over ? "pointer" : "";
        });
      };
      const onContextMenu = (event: MapMouseEvent): void => {
        event.preventDefault();
        latest.current.navigate(elsewherePath(event.lngLat.lng, event.lngLat.lat));
      };
      map.on("click", onClick);
      map.on("mousemove", onMove);
      map.on("contextmenu", onContextMenu);
      detach.push(() => {
        cancelAnimationFrame(frame);
        map.off("click", onClick);
        map.off("mousemove", onMove);
        map.off("contextmenu", onContextMenu);
      });
    }
    if (main && isMapLive(main)) {
      const report = (): void => {
        if (isMapLive(main)) useRecordsOnScreen.getState().setSources(sourcesOf(query(main, CREDITED)));
      };
      main.on("idle", report);
      detach.push(() => main.off("idle", report));
    }
    return () => {
      for (const off of detach) off();
    };
  }, [main, compare]);
}
