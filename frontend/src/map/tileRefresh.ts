import { useQuery } from "@tanstack/react-query";
import type { Map as MapLibreMap } from "maplibre-gl";
import { useEffect } from "react";
import type { Meta } from "../api/meta.js";
import { fetchMeta } from "../api/useMeta.js";
import { isMapLive } from "./MapPane.js";
import { absoluteUrl, DEM_SOURCE, DEM_TERRAIN_SOURCE, viewSourceId } from "./style.js";

/**
 * Terrain tile addresses carry a version token (`?v=`) that changes when the
 * rendering or the data does, so a tile asked for with the current token can
 * be cached for good. A page left open across such a change would go on
 * asking for the old token. Every so often, and when the page comes back into
 * view, the catalogue is asked for again, and any source whose addresses have
 * changed is given the new ones, which reloads it.
 */

/** How often the catalogue is checked for new tile addresses while the page is open. */
export const TILE_CHECK_MS = 30 * 60_000;
export const TILE_CHECK_KEY = ["meta", "tiles"] as const;

/** The tile addresses of every tiled source the map builds from a catalogue, by source id. */
export function tileAddresses(meta: Meta): Map<string, readonly string[]> {
  const found = new Map<string, readonly string[]>();
  for (const view of meta.layers.views) {
    if (view.type === "raster") found.set(viewSourceId(view.id), view.tiles);
  }
  found.set(DEM_SOURCE, meta.layers.dem.tiles);
  found.set(DEM_TERRAIN_SOURCE, meta.layers.dem.tiles);
  return found;
}

/**
 * The sources whose addresses differ between the catalogue the map was built
 * from and a fresh one, with their new addresses. A source the fresh
 * catalogue lacks is left alone: a catalogue that changes shape needs a reload.
 */
export function changedTiles(built: Meta, fresh: Meta): Map<string, readonly string[]> {
  const before = tileAddresses(built);
  const changed = new Map<string, readonly string[]>();
  for (const [source, tiles] of tileAddresses(fresh)) {
    const old = before.get(source);
    if (old && (old.length !== tiles.length || old.some((url, i) => url !== tiles[i]))) changed.set(source, tiles);
  }
  return changed;
}

interface TileSource {
  setTiles(tiles: string[]): unknown;
}

function hasSetTiles(source: unknown): source is TileSource {
  return typeof source === "object" && source !== null && typeof (source as TileSource).setTiles === "function";
}

/** Give each changed source on a live map its new addresses. MapLibre drops its tiles and loads them again. */
export function applyTileChanges(
  map: Pick<MapLibreMap, "getSource">,
  changes: ReadonlyMap<string, readonly string[]>,
  origin: string,
): void {
  for (const [sourceId, tiles] of changes) {
    const source = map.getSource(sourceId);
    if (hasSetTiles(source)) source.setTiles(tiles.map((url) => absoluteUrl(url, origin)));
  }
}

/**
 * Keep the map's tile addresses current while the page is open. `meta` is the
 * catalogue the panes were built from; the panes are not rebuilt.
 */
export function useTileRefresh(meta: Meta, maps: ReadonlyArray<MapLibreMap | null>): void {
  const fresh = useQuery({
    queryKey: TILE_CHECK_KEY,
    queryFn: ({ signal }) => fetchMeta(signal),
    // The catalogue on hand is current when the page opens. Checking starts later.
    initialData: meta,
    initialDataUpdatedAt: Date.now(),
    staleTime: TILE_CHECK_MS,
    refetchInterval: TILE_CHECK_MS,
    refetchOnWindowFocus: true,
    retry: false,
  });
  const latest = fresh.data;
  const [first, second] = maps;

  useEffect(() => {
    if (latest === meta) return;
    const changes = changedTiles(meta, latest);
    if (changes.size === 0) return;
    for (const map of [first, second]) {
      if (map && isMapLive(map)) applyTileChanges(map, changes, window.location.origin);
    }
  }, [meta, latest, first, second]);
}
