import { useQueries } from "@tanstack/react-query";
import { useEffect, useMemo, useRef } from "react";
import { useOptionalEndpointQuery } from "../../../api/useOptionalEndpointQuery.js";
import { useViewAreaStore } from "../../../map/store.js";
import { useDebounced } from "../../../ui/useDebounced.js";
import { fetchLiveSources, recordKeys } from "../api.js";
import type { Feature, FeatureCollection } from "../geojson.js";
import { useRecordsOnScreen } from "../onScreen.js";
import { type LiveArea, type LiveSource, liveSourcesFrom } from "./catalogue.js";
import { fetchLiveRecords, LiveSourceError } from "./client.js";
import { type LiveStatus, useLiveStore } from "./store.js";

/** How long the map must hold still before the live sources are asked about the view. */
export const LIVE_SETTLE_MS = 600;
/** An answer for one area is used again for this long, so panning back costs nothing. */
const LIVE_STALE_MS = 5 * 60_000;

/** The catalogue of live sources, from `GET /context/live-sources`. Asked for only when `wanted`. */
export function useLiveCatalogue(wanted: boolean): { sources: LiveSource[]; loading: boolean; failed: boolean } {
  const { query, missing } = useOptionalEndpointQuery({
    queryKey: recordKeys.liveSources,
    queryFn: ({ signal }) => fetchLiveSources(signal),
    enabled: wanted,
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
  });
  const sources = useMemo(() => liveSourcesFrom(query.data ?? []), [query.data]);
  return { sources: missing ? [] : sources, loading: query.isLoading, failed: query.isError && !missing };
}

/**
 * The view, to about a hundred metres, and its whole zoom, as text so it can
 * be compared and debounced.
 */
function viewKey(bounds: readonly [number, number, number, number], zoom: number): string {
  return `${bounds.map((value) => value.toFixed(3)).join(",")}@${Math.floor(zoom)}`;
}

function viewFrom(key: string): { area: string; zoom: number } {
  const [area = "", zoom = "0"] = key.split("@");
  return { area, zoom: Number(zoom) };
}

function areaFrom(key: string): LiveArea {
  const [west, south, east, north] = key.split(",").map(Number) as [number, number, number, number];
  return { west, south, east, north };
}

const NO_RECORDS: FeatureCollection = { type: "FeatureCollection", features: [] };

/**
 * Ask every live source that is on about the area in view, once the map has
 * settled at the source's lowest zoom or closer, and return what they sent as
 * map features. Each source is asked once per area, and a request for an
 * area the map has left is cancelled. Nothing is retried: a source that
 * fails is turned off, with its reason kept for the layer panel.
 *
 * `shown` is false while the records overlay is off, and then nothing is asked.
 */
export function useLiveRecords(shown: boolean): FeatureCollection {
  const on = useLiveStore((state) => state.on);
  const anyOn = Object.values(on).some(Boolean);
  const { sources } = useLiveCatalogue(anyOn);
  const bounds = useViewAreaStore((state) => state.bounds);
  const zoom = useViewAreaStore((state) => state.zoom);

  const active = useMemo(() => sources.filter((source) => on[source.key]), [sources, on]);
  const lowest = Math.min(...active.map((source) => source.minZoom));
  const wanted = shown && bounds !== null && zoom >= lowest ? viewKey(bounds, zoom) : null;
  const settled = useDebounced(wanted, LIVE_SETTLE_MS, null);
  // A view that has since been left, or zoomed out of, is not asked about.
  const view = wanted === null || settled === null ? null : viewFrom(settled);
  const area = view?.area ?? null;

  const results = useQueries({
    queries: active.map((source) => ({
      queryKey: recordKeys.live(source.key, area ?? ""),
      queryFn: ({ signal }: { signal: AbortSignal }) => {
        if (area === null) throw new Error("A live source was asked with no area");
        return fetchLiveRecords(source, areaFrom(area), signal);
      },
      enabled: area !== null && view !== null && view.zoom >= source.minZoom,
      retry: false,
      staleTime: LIVE_STALE_MS,
      gcTime: LIVE_STALE_MS,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
    })),
  });

  // Each source's state, worked out once per render and reported only when it changes.
  const statuses: Array<[LiveSource, LiveStatus]> = active.map((source, index) => {
    const result = results[index];
    if (area === null || !result || view === null || view.zoom < source.minZoom) return [source, { state: "idle" }];
    if (result.isError) {
      const error = result.error;
      const kind = error instanceof LiveSourceError ? error.kind : "failed";
      return [
        source,
        { state: kind, message: error instanceof LiveSourceError ? error.message : "Something went wrong." },
      ];
    }
    if (result.data && !result.isFetching) {
      return [source, { state: "ready", records: result.data.records, truncated: result.data.truncated }];
    }
    return [source, { state: "loading" }];
  });

  useEffect(() => {
    const store = useLiveStore.getState();
    for (const [source, status] of statuses) {
      if (status.state === "refused" || status.state === "failed") store.fail(source.key, status);
      else store.report(source.key, status);
    }
  });

  const ready = statuses.filter(
    (entry): entry is [LiveSource, Extract<LiveStatus, { state: "ready" }>] =>
      entry[1].state === "ready" && entry[1].records.length > 0,
  );
  // Answers for one source and area never change, so this names the records exactly.
  const signature = `${area}|${ready.map(([source, status]) => `${source.key}:${status.records.length}`).join("|")}`;
  const drawn = useRef<{ signature: string; collection: FeatureCollection; credits: string } | null>(null);
  if (drawn.current?.signature !== signature) {
    const features: Feature[] = [];
    for (const [source, status] of ready) {
      for (const record of status.records) {
        features.push({
          type: "Feature",
          geometry: { type: "Point", coordinates: [record.lon, record.lat] },
          properties: { source: source.key, id: record.id, name: record.name },
        });
      }
    }
    drawn.current = {
      signature,
      collection: features.length > 0 ? { type: "FeatureCollection", features } : NO_RECORDS,
      credits: ready.map(([source]) => source.attribution).join("\n"),
    };
  }
  const { collection, credits } = drawn.current;

  useEffect(() => {
    useRecordsOnScreen.getState().setLiveAttributions(credits === "" ? [] : credits.split("\n"));
  }, [credits]);

  return collection;
}
