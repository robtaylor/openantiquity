import type { Map as MapLibreMap, MapSourceDataEvent, MapStyleDataEvent } from "maplibre-gl";

type MapDataEvent = MapSourceDataEvent | MapStyleDataEvent;

import { useEffect } from "react";
import { create } from "zustand";
import { findView, type Meta } from "../../api/meta.js";
import { isMapLive } from "../../map/MapPane.js";
import { useMapStore } from "../../map/store.js";
import { DEM_SOURCE, viewSourceId } from "../../map/style.js";

/**
 * How long a terrain view may go on loading before the map says it is
 * being prepared. A cached tile arrives well within this. A first look at an
 * area waits for a source tile to be fetched and rendered, which takes 8 to
 * 18 seconds (Decision 0006, Consequences), and without a word that looks
 * like a black map.
 */
export const PREPARING_AFTER_MS = 1500;

/**
 * Terrain tiles from this zoom up are drawn from the one-metre mirror, and
 * fetched when missing. Below it they come from the national 10 m composite
 * or, until that is built, only from tiles already mirrored, so much of a
 * zoomed-out view can be blank (docs/ARCHITECTURE.md, Terrain). `/meta`
 * says this as `terrain.fine_minzoom`; this is the fallback for a server that
 * doesn't.
 */
export const TERRAIN_DETAIL_ZOOM = 13;

interface TerrainLoadingState {
  /** True while the terrain in view has been loading for longer than `PREPARING_AFTER_MS`. */
  preparing: boolean;
  setPreparing: (preparing: boolean) => void;
}

export const useTerrainLoading = create<TerrainLoadingState>()((set, get) => ({
  preparing: false,
  setPreparing: (preparing) => {
    if (get().preparing !== preparing) set({ preparing });
  },
}));

/** The map source that holds the pixels of a terrain view, or null for a view that isn't terrain. */
export function terrainSourceOf(meta: Meta, viewId: string): string | null {
  const view = findView(meta, viewId);
  if (view?.group !== "lidar") return null;
  return view.type === "raking" ? DEM_SOURCE : viewSourceId(view.id);
}

/**
 * Watches the main map's terrain source. Once it has been loading for a
 * while, `useTerrainLoading` says so; when its tiles are in, or the map is
 * idle, it stops saying so.
 */
export function useTerrainLoadingOnMap(meta: Meta, main: MapLibreMap | null): void {
  useEffect(() => {
    if (!main || !isMapLive(main)) return;
    const { setPreparing } = useTerrainLoading.getState();
    let timer: ReturnType<typeof setTimeout> | null = null;
    const watched = (event: MapDataEvent): boolean =>
      event.dataType === "source" && event.sourceId === terrainSourceOf(meta, useMapStore.getState().mainView);
    const settle = (): void => {
      if (timer !== null) clearTimeout(timer);
      timer = null;
      setPreparing(false);
    };
    const onLoading = (event: MapDataEvent): void => {
      if (!watched(event) || timer !== null || useTerrainLoading.getState().preparing) return;
      timer = setTimeout(() => {
        timer = null;
        setPreparing(true);
      }, PREPARING_AFTER_MS);
    };
    const onData = (event: MapDataEvent): void => {
      if (watched(event) && event.dataType === "source" && event.isSourceLoaded) settle();
    };
    main.on("dataloading", onLoading);
    main.on("sourcedata", onData);
    main.on("idle", settle);
    return () => {
      main.off("dataloading", onLoading);
      main.off("sourcedata", onData);
      main.off("idle", settle);
      settle();
    };
  }, [meta, main]);
}
