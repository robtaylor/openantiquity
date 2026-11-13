import { type GeoJSONSource, type MapEventType, Map as MapLibreMap, type StyleSpecification } from "maplibre-gl";
import { type CSSProperties, memo, useEffect, useRef, useState } from "react";
import { findOverlay, findView, type Meta } from "../api/meta.js";
import type { FindingsMapData } from "./findingsData.js";
import { MapFailure } from "./MapFailure.js";
import { SDF_IMAGE_OPTIONS, squareSdf } from "./markerImages.js";
import { recordsCountsSourceId, SQUARE_IMAGE } from "./overlayLayers.js";
import { LIMITS } from "./permalink.js";
import { reloadSource, type SourceDeclaration } from "./reloadSource.js";
import { changedAny, useMapStore, usePointerStore, useViewAreaStore } from "./store.js";
import {
  applyMapState,
  applyTerrain,
  buildStyle,
  DEM_SOURCE,
  DEM_TERRAIN_SOURCE,
  overlaySourceId,
  STYLE_KEYS,
  terrainChange,
  viewSourceId,
} from "./style.js";
import { isSettledMove, isSyncedMove } from "./syncMaps.js";
import { createTileHealth } from "./tileErrors.js";
import { DEM_TROUBLE_KEY, overlayTroubleKey, viewTroubleKey } from "./trouble.js";

export interface MapPaneProps {
  meta: Meta;
  /** The view this pane shows. */
  viewId: string;
  /**
   * The main pane obeys camera requests. Either pane records where the map
   * is when it is the one being moved, and the other follows.
   */
  pane: "main" | "compare";
  /** The findings to draw, from `useFindingsOverlay`. */
  findings: FindingsMapData;
  style?: CSSProperties;
  /** Called with the map once its style has loaded, and with null when it goes. */
  onMap: (map: MapLibreMap | null) => void;
}

const EASE_MS = 600;
/** How long after a touch a mouse event is taken to be the browser's echo of it. */
const GHOST_MOUSE_MS = 1000;
/**
 * How long the 3D height setting must hold still before the terrain is
 * rebuilt for it. Each rebuild allocates a full set of framebuffers, so it
 * waits for the slider to settle.
 */
export const TERRAIN_SETTLE_MS = 250;

/** Why a pane has no map to show. */
interface Failure {
  /** "webgl": the browser gave no graphics context. "catalogue": the layers from /meta could not be turned into a map. */
  kind: "webgl" | "catalogue";
  detail: string;
}

const removedMaps = new WeakSet<object>();

/**
 * False once a pane has removed its map. MapLibre throws from most methods of
 * a removed map and still calls its listeners, so anything holding a map
 * across renders checks here first.
 */
export function isMapLive(map: object): boolean {
  return !removedMaps.has(map);
}

function prefersReducedMotion(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function messageOf(cause: unknown): string {
  return cause instanceof Error ? cause.message : String(cause);
}

/** The sources whose loading is watched, each with the trouble key it is marked under in the store. */
function watchedSources(meta: Meta): Record<string, string> {
  const watched: Record<string, string> = {};
  for (const overlay of meta.layers.overlays) {
    // Coverage and findings are drawn from data the app fetches itself, not from tiles.
    if (overlay.type === "coverage" || overlay.type === "findings") continue;
    watched[overlaySourceId(overlay.id)] = overlayTroubleKey(overlay.id);
    // The records' zoomed-out counts come from a second source over the same tiles, and fail with them.
    if (overlay.type === "records") {
      watched[recordsCountsSourceId(overlaySourceId(overlay.id))] = overlayTroubleKey(overlay.id);
    }
  }
  for (const view of meta.layers.views) {
    if (view.type === "raster") watched[viewSourceId(view.id)] = viewTroubleKey(view.id);
  }
  watched[DEM_SOURCE] = DEM_TROUBLE_KEY;
  watched[DEM_TERRAIN_SOURCE] = DEM_TROUBLE_KEY;
  return watched;
}

/**
 * One MapLibre instance showing one view, kept in step with the map store.
 * Memoised, so that a swipe or a new view area re-renders only a pane whose
 * own props changed.
 */
export const MapPane = memo(function MapPane({ meta, viewId, pane: paneRole, findings, style, onMap }: MapPaneProps) {
  const pane = useRef<HTMLDivElement>(null);
  const container = useRef<HTMLDivElement>(null);
  const viewIdRef = useRef(viewId);
  const applyRef = useRef<(() => void) | null>(null);
  const findingsRef = useRef(findings);
  const applyFindingsRef = useRef<(() => void) | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  /** Bumped to throw the map away and make a new one. */
  const [attempt, setAttempt] = useState(0);

  // biome-ignore lint/correctness/useExhaustiveDependencies: a new attempt is the trigger
  useEffect(() => {
    const element = pane.current;
    const canvasHost = container.current;
    if (!element || !canvasHost) throw new Error("MapPane mounted without its container");
    const initial = useMapStore.getState();
    if (initial.meta === null) throw new Error("MapPane mounted before the map store was initialised");

    // A fault in the layer catalogue shows itself here, before WebGL comes into it.
    let styleSpec: StyleSpecification;
    try {
      styleSpec = buildStyle(meta, initial, viewIdRef.current);
    } catch (cause) {
      setFailure({ kind: "catalogue", detail: messageOf(cause) });
      return;
    }

    // Reloading needs only each source's type and address. Keeping just those
    // lets the full style go once MapLibre has its own copy.
    const declarations = new Map<string, SourceDeclaration>(
      Object.entries(styleSpec.sources).map(([id, source]) => [
        id,
        { type: source.type, url: "url" in source ? source.url : undefined },
      ]),
    );

    let map: MapLibreMap;
    try {
      map = new MapLibreMap({
        container: canvasHost,
        style: styleSpec,
        center: [initial.camera.lng, initial.camera.lat],
        zoom: initial.camera.zoom,
        bearing: initial.camera.bearing,
        pitch: initial.camera.pitch,
        maxPitch: LIMITS.pitch.max,
        minZoom: LIMITS.zoom.min,
        maxZoom: LIMITS.zoom.max,
        // Attribution is drawn by the status bar and the layer panel, from /meta.
        attributionControl: false,
        // Each source's symbols are placed among themselves. Placed together, the record counts
        // took the room of the street map's names, and a city went unnamed under its own count.
        crossSourceCollisions: false,
        // The permalink is richer than MapLibre's own hash, so it is handled in usePermalink.
        hash: false,
        fadeDuration: 150,
      });
    } catch (cause) {
      // MapLibre throws here when the browser cannot give it a WebGL context.
      setFailure({ kind: "webgl", detail: messageOf(cause) });
      return;
    }
    setFailure(null);

    let disposed = false;
    let styleReady = false;

    /** Listen to the map until this pane lets go of it. A removed map still fires events, and throws if asked anything. */
    function listen<T extends keyof MapEventType>(type: T, listener: (event: MapEventType[T] & object) => void): void {
      map.on(type, (event) => {
        if (!disposed) listener(event);
      });
    }

    const watched = watchedSources(meta);
    const findingsOverlay = findOverlay(meta, "findings");
    const findingsSource = findingsOverlay ? overlaySourceId(findingsOverlay.id) : null;

    let terrainTimer: ReturnType<typeof setTimeout> | undefined;
    function cancelTerrainTimer(): void {
      if (terrainTimer !== undefined) clearTimeout(terrainTimer);
      terrainTimer = undefined;
    }

    /** What this map's style was last given, so a slider tick sends only what it changed. */
    const applied = new Map<string, unknown>();
    function apply(): void {
      if (!styleReady || disposed) return;
      const state = useMapStore.getState();
      applyMapState(map, meta, state, viewIdRef.current, { terrain: "leave", applied });
      // Switching 3D on or off happens at once. A new height setting waits for the slider to stop.
      const change = terrainChange(map, state);
      cancelTerrainTimer();
      if (change === "switch") applyTerrain(map, state);
      else if (change === "rebuild") {
        terrainTimer = setTimeout(() => {
          terrainTimer = undefined;
          if (!disposed) applyTerrain(map, useMapStore.getState());
        }, TERRAIN_SETTLE_MS);
      }
      const title = findView(meta, viewIdRef.current)?.title;
      map.getCanvas().setAttribute("aria-label", title ? `Map: ${title}` : "Map");
    }
    applyRef.current = apply;

    function addImages(): void {
      if (!map.hasImage(SQUARE_IMAGE)) map.addImage(SQUARE_IMAGE, squareSdf(), SDF_IMAGE_OPTIONS);
    }

    let shownFindings: FindingsMapData | null = null;
    function applyFindings(): void {
      if (!styleReady || disposed || findingsSource === null) return;
      if (findingsRef.current === shownFindings) return;
      const source = map.getSource(findingsSource) as GeoJSONSource | undefined;
      if (!source) return;
      shownFindings = findingsRef.current;
      source.setData(shownFindings);
    }
    applyFindingsRef.current = applyFindings;

    /** Tell the rest of the app what area the map shows, so it can ask the server what is in it. */
    function recordArea(): void {
      if (paneRole !== "main" || !styleReady) return;
      const bounds = map.getBounds();
      useViewAreaStore
        .getState()
        .setArea([bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()], map.getZoom());
    }

    function recordCamera(): void {
      const centre = map.getCenter();
      useMapStore.getState().setCamera({
        lng: centre.lng,
        lat: centre.lat,
        zoom: map.getZoom(),
        bearing: map.getBearing(),
        pitch: map.getPitch(),
      });
    }

    function reload(sourceId: string): void {
      if (disposed || !styleReady) return;
      const declaration = declarations.get(sourceId);
      if (declaration) reloadSource(map, sourceId, declaration);
    }

    // Leaving the page cancels every tile still in flight, and each one would
    // be reported as a failure. Nothing has gone wrong, so say nothing.
    let leaving = false;
    const onLeave = (): void => {
      leaving = true;
    };
    const onReturn = (): void => {
      leaving = false;
    };
    // Something on the page may ask "leave this page?" (marking does, with a
    // line not yet kept). When the person stays, the page is still here a
    // moment later, and tiles are reported again.
    const onBeforeUnload = (event: Event): void => {
      leaving = true;
      window.setTimeout(() => {
        if (event.defaultPrevented) leaving = false;
      }, 0);
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    window.addEventListener("pagehide", onLeave);
    window.addEventListener("pageshow", onReturn);

    function mark(sourceId: string, failing: boolean): void {
      const key = watched[sourceId];
      if (key !== undefined) useMapStore.getState().setSourceFailing(key, failing);
    }

    const health = createTileHealth({
      reload,
      onFailing: (sourceId) => mark(sourceId, true),
      onRecovered: (sourceId) => mark(sourceId, false),
      warn: (message) => console.warn(message),
    });

    map.once("styledata", () => {
      if (disposed) return;
      styleReady = true;
      addImages();
      apply();
      applyFindings();
      // The map may not be where it was asked to be: it keeps to its own limits. The store takes its word.
      if (paneRole === "main") recordCamera();
      recordArea();
      onMap(map);
    });
    // "idle" means every tile in view has arrived and been drawn. Tests and
    // screenshots wait on it.
    listen("idle", () => {
      element.dataset.mapIdle = "true";
    });
    listen("dataloading", () => {
      element.dataset.mapIdle = "false";
    });
    // From MapLibre 6 the "styleimagemissing" event only reports. A missing image is supplied here.
    map.setMissingStyleImageResolver((id) => {
      if (!disposed && id === SQUARE_IMAGE) addImages();
    });
    listen("sourcedata", (event) => {
      if (event.tile && !leaving) health.onTileLoaded(event.sourceId);
    });
    listen("error", (event) => {
      if (leaving) return;
      const source = (event as { sourceId?: unknown }).sourceId;
      // Before the style is in, the only thing that can fail is the style: MapLibre has refused the catalogue.
      if (!styleReady && source === undefined) {
        setFailure({ kind: "catalogue", detail: event.error?.message ?? "The map style was refused." });
        return;
      }
      health.onError(event as { error?: { message?: string; status?: number }; sourceId?: unknown; tile?: unknown });
    });

    // Counts the camera requests passed on to the map. Each move made for one carries its number.
    let requestsSent = 0;

    listen("moveend", (event) => {
      // A move copied from the other pane is not this map's own: the pane
      // being moved records it. Without this, dragging one pane had the
      // other writing the camera to the store on every frame.
      if (isSyncedMove(event)) {
        if (isSettledMove(event)) recordArea();
        return;
      }
      recordArea();
      // A requested move cut short by a later request ends here, part-way.
      // The store already holds where the later one is going, and writing
      // this half-way camera over it would send the next request, such as a
      // third press of a zoom button, off from the wrong place.
      const request = (event as { cameraRequest?: unknown }).cameraRequest;
      if (request !== undefined && request !== requestsSent) return;
      if (styleReady) recordCamera();
    });
    // A wider window shows more, with no move at all.
    listen("resize", recordArea);

    // The readout follows a mouse. A finger is not a pointer that hovers, and
    // browsers follow each tap with made-up mouse events, so those are ignored
    // and the readout falls back to the centre of the map.
    const pointer = usePointerStore.getState();
    let lastTouch = Number.NEGATIVE_INFINITY;
    const onTouch = (): void => {
      lastTouch = performance.now();
      pointer.setPosition(null);
    };
    listen("touchstart", onTouch);
    listen("touchend", onTouch);
    listen("mousemove", (event) => {
      if (performance.now() - lastTouch < GHOST_MOUSE_MS) return;
      pointer.setPosition({ lng: event.lngLat.lng, lat: event.lngLat.lat });
    });
    listen("mouseout", () => pointer.setPosition(null));

    const unsubscribe = useMapStore.subscribe((next, previous) => {
      if (changedAny(next, previous, STYLE_KEYS)) apply();
      if (styleReady && next.retries !== previous.retries) {
        for (const [sourceId, key] of Object.entries(watched)) {
          if (next.retries[key] === previous.retries[key]) continue;
          health.retried(sourceId);
          reload(sourceId);
        }
      }
      if (paneRole === "main" && next.cameraRequest !== previous.cameraRequest) {
        const target = {
          center: [next.camera.lng, next.camera.lat] as [number, number],
          zoom: next.camera.zoom,
          bearing: next.camera.bearing,
          pitch: next.camera.pitch,
        };
        requestsSent += 1;
        const eventData = { cameraRequest: requestsSent };
        if (prefersReducedMotion()) map.jumpTo(target, eventData);
        else map.easeTo({ ...target, duration: EASE_MS }, eventData);
      }
    });

    return () => {
      // Set first: map.remove() and the calls below can each set off a listener.
      disposed = true;
      removedMaps.add(map);
      unsubscribe();
      health.dispose();
      cancelTerrainTimer();
      window.removeEventListener("beforeunload", onBeforeUnload);
      window.removeEventListener("pagehide", onLeave);
      window.removeEventListener("pageshow", onReturn);
      applyRef.current = null;
      applyFindingsRef.current = null;
      onMap(null);
      map.remove();
    };
  }, [meta, paneRole, onMap, attempt]);

  useEffect(() => {
    viewIdRef.current = viewId;
    applyRef.current?.();
  }, [viewId]);

  useEffect(() => {
    findingsRef.current = findings;
    applyFindingsRef.current?.();
  }, [findings]);

  return (
    <div ref={pane} className={`fc-map__pane fc-map__pane--${paneRole}`} style={style} data-view={viewId}>
      <div ref={container} className="fc-map__canvas" />
      {failure?.kind === "webgl" ? (
        <MapFailure
          title="The map can't be drawn here"
          actionLabel="Try again"
          onAction={() => setAttempt((n) => n + 1)}
          detail={failure.detail}
        >
          <p>
            This browser didn't give the map the graphics support it needs (WebGL). Try another browser, or switch
            hardware acceleration on.
          </p>
        </MapFailure>
      ) : null}
      {failure?.kind === "catalogue" ? (
        <MapFailure
          title="The map's layers couldn't be set up"
          actionLabel="Reload the page"
          onAction={() => window.location.reload()}
          detail={failure.detail}
        >
          <p>
            The list of map layers this site sent has a fault in it, so there is nothing to draw. That's a problem at
            our end, not with your browser. Reloading fetches the list again.
          </p>
        </MapFailure>
      ) : null}
    </div>
  );
});
