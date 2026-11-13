import { create } from "zustand";
import { defaultView, findView, type Meta, type Overlay, type OverlayType } from "../api/meta.js";
import { clamp, wrapDegrees } from "../ui/math.js";
import {
  type CameraState,
  LIMITS,
  type OverlayState,
  PERMALINK_KEYS,
  type PermalinkState,
  type SunState,
  type TerrainState,
} from "./permalink.js";

export { DEM_TROUBLE_KEY, overlayTroubleKey, viewTroubleKey } from "./trouble.js";

export class MapStateError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "MapStateError";
  }
}

/** Which overlays are on when nothing else says so. */
const DEFAULT_VISIBLE: Record<OverlayType, boolean> = {
  openmaptiles: true,
  records: true,
  findings: true,
  coverage: false,
};

/**
 * Light from the north-west, low. Checked against the 1 m tiles at Fyfield
 * Down in November 2026: at 20 degrees the low field banks and ridges show,
 * where 25 and higher wash them out and 15 burns the lit slopes white.
 */
export const DEFAULT_SUN: SunState = { azimuth: 315, altitude: 20 };
export const DEFAULT_HILLSHADE_EXAGGERATION = 2;
export const DEFAULT_TERRAIN: TerrainState = { enabled: false, exaggeration: 1.5 };
/** Pitch applied when 3D is switched on from a flat view. */
export const TERRAIN_PITCH = 60;

export interface MapState extends PermalinkState {
  /** The catalogue the state was built from. Null until `initialise` runs. */
  meta: Meta | null;
  /** Position of the comparison handle, 0 (left edge) to 1 (right edge). */
  swipe: number;
  /**
   * Sources that are not loading, by trouble key: `overlayTroubleKey(id)` for
   * an overlay, which stays off until retried, `viewTroubleKey(id)` for a
   * view, and `DEM_TROUBLE_KEY` for the elevation data.
   */
  failing: Record<string, boolean>;
  /** How many times each source has been asked to try again, by trouble key. The map reloads it on each. */
  retries: Record<string, number>;
  /** Bumped by `requestCamera` so the map knows to move. */
  cameraRequest: number;
  /** Overlays held off the map for now, whatever their switches say. See `StyleState.held`. */
  held: readonly string[];

  initialise: (meta: Meta, permalink?: Partial<PermalinkState>) => void;
  applyPermalink: (permalink: Partial<PermalinkState>) => void;
  setMainView: (id: string) => void;
  setCompareView: (id: string | null) => void;
  toggleCompare: () => void;
  swapViews: () => void;
  setSwipe: (position: number) => void;
  setOverlayVisible: (id: string, visible: boolean) => void;
  setOverlayOpacity: (id: string, opacity: number) => void;
  /** Mark a source as failing to load, or clear the mark. Clearing it does not ask for another attempt. */
  setSourceFailing: (key: string, failing: boolean) => void;
  /** Clear a source's mark and have it tried again. Does nothing for a source that is not marked. */
  retrySource: (key: string) => void;
  /** Hold an overlay off the map, or let it back. Its switch is left as it was. */
  holdOverlay: (id: string, held: boolean) => void;
  setSun: (sun: Partial<SunState>) => void;
  setHillshadeExaggeration: (value: number) => void;
  setTerrainEnabled: (enabled: boolean) => void;
  setTerrainExaggeration: (value: number) => void;
  setShowRuledOut: (show: boolean) => void;
  /** Draw heritage records as counts where the map is zoomed out too far for single records, or not. */
  setShowRecordCounts: (show: boolean) => void;
  /** Record where the map is. Called by the map itself. */
  setCamera: (camera: CameraState) => void;
  /** Ask the map to move. Called by everything else. */
  requestCamera: (camera: Partial<CameraState>) => void;
  /** Zoom in (positive) or out (negative) by this many levels, within the limits. */
  zoomBy: (levels: number) => void;
  /** Turn the map north-up. The tilt stays as it is, so a 3D view stays 3D. */
  resetNorth: () => void;
}

function finite(value: number, name: string): number {
  if (!Number.isFinite(value)) throw new MapStateError(`${name} must be a finite number, got ${value}`);
  return value;
}

function defaultOverlayState(overlay: Overlay): OverlayState {
  return {
    visible: DEFAULT_VISIBLE[overlay.type],
    opacity: clamp(overlay.default_opacity ?? 1, 0, 1),
  };
}

/** The values a fresh map starts with, before any permalink is applied. */
export function defaultsFromMeta(meta: Meta): PermalinkState {
  const [lng, lat] = meta.layers.initial_view.center;
  const overlays: Record<string, OverlayState> = {};
  for (const overlay of meta.layers.overlays) overlays[overlay.id] = defaultOverlayState(overlay);
  return {
    camera: { lng, lat, zoom: meta.layers.initial_view.zoom, bearing: 0, pitch: 0 },
    mainView: defaultView(meta).id,
    compareView: null,
    sun: { ...DEFAULT_SUN },
    hillshadeExaggeration: DEFAULT_HILLSHADE_EXAGGERATION,
    terrain: { ...DEFAULT_TERRAIN },
    overlays,
    showRuledOut: false,
    showRecordCounts: false,
  };
}

/**
 * Lay a decoded permalink over a known-good state. Ids the catalogue does not
 * have are dropped, so an old link to a retired layer still opens the map.
 */
export function mergePermalink(base: PermalinkState, permalink: Partial<PermalinkState>, meta: Meta): PermalinkState {
  const known = (id: string): boolean => findView(meta, id) !== undefined;
  const mainView = permalink.mainView !== undefined && known(permalink.mainView) ? permalink.mainView : base.mainView;
  let compareView = base.compareView;
  if (permalink.compareView !== undefined) {
    compareView = permalink.compareView !== null && known(permalink.compareView) ? permalink.compareView : null;
  }
  if (compareView === mainView) compareView = null;

  const overlays: Record<string, OverlayState> = { ...base.overlays };
  for (const [id, overlay] of Object.entries(permalink.overlays ?? {})) {
    if (meta.layers.overlays.some((candidate) => candidate.id === id))
      overlays[id] = { visible: overlay.visible, opacity: clamp(overlay.opacity, 0, 1) };
  }

  return {
    camera: permalink.camera ? { ...permalink.camera } : base.camera,
    mainView,
    compareView,
    sun: permalink.sun ? { ...permalink.sun } : base.sun,
    hillshadeExaggeration: permalink.hillshadeExaggeration ?? base.hillshadeExaggeration,
    terrain: permalink.terrain ? { ...permalink.terrain } : base.terrain,
    overlays,
    showRuledOut: permalink.showRuledOut ?? base.showRuledOut,
    showRecordCounts: permalink.showRecordCounts ?? base.showRecordCounts,
  };
}

/**
 * Pick a sensible layer to compare against: the first view from a different
 * group, so a swipe starts as terrain against a map or photo, falling back to
 * any other view.
 */
export function pickCompareView(meta: Meta, mainView: string): string | null {
  const main = findView(meta, mainView);
  const others = meta.layers.views.filter((view) => view.id !== mainView);
  const otherGroup = others.find((view) => view.group !== main?.group);
  return (otherGroup ?? others[0])?.id ?? null;
}

export const useMapStore = create<MapState>()((set, get) => {
  function requireReady(): Meta {
    const { meta } = get();
    if (!meta) throw new MapStateError("The map store was used before initialise()");
    return meta;
  }

  function requireView(id: string): void {
    if (!findView(requireReady(), id)) throw new MapStateError(`Unknown view "${id}"`);
  }

  function requireOverlay(id: string): OverlayState {
    requireReady();
    const overlay = get().overlays[id];
    if (!overlay) throw new MapStateError(`Unknown overlay "${id}"`);
    return overlay;
  }

  return {
    meta: null,
    swipe: 0.5,
    failing: {},
    retries: {},
    cameraRequest: 0,
    held: [],
    camera: { lng: 0, lat: 0, zoom: 0, bearing: 0, pitch: 0 },
    mainView: "",
    compareView: null,
    sun: { ...DEFAULT_SUN },
    hillshadeExaggeration: DEFAULT_HILLSHADE_EXAGGERATION,
    terrain: { ...DEFAULT_TERRAIN },
    overlays: {},
    showRuledOut: false,
    showRecordCounts: false,

    initialise: (meta, permalink = {}) => {
      set({
        ...mergePermalink(defaultsFromMeta(meta), permalink, meta),
        meta,
        swipe: 0.5,
        failing: {},
        retries: {},
      });
    },

    applyPermalink: (permalink) => {
      const meta = requireReady();
      const state = get();
      const merged = mergePermalink(state, permalink, meta);
      set({ ...merged, cameraRequest: permalink.camera ? state.cameraRequest + 1 : state.cameraRequest });
    },

    setMainView: (id) => {
      requireView(id);
      const { mainView, compareView } = get();
      if (id === mainView) return;
      // Choosing the comparison layer as the main one swaps the two.
      set(id === compareView ? { mainView: id, compareView: mainView } : { mainView: id });
    },

    setCompareView: (id) => {
      if (id === null) {
        requireReady();
        set({ compareView: null });
        return;
      }
      requireView(id);
      const { mainView, compareView } = get();
      if (id === compareView) return;
      if (id === mainView) {
        if (compareView === null) throw new MapStateError("A layer cannot be compared with itself");
        set({ mainView: compareView, compareView: id });
        return;
      }
      set({ compareView: id });
    },

    toggleCompare: () => {
      const meta = requireReady();
      const { mainView, compareView } = get();
      set({ compareView: compareView === null ? pickCompareView(meta, mainView) : null, swipe: 0.5 });
    },

    swapViews: () => {
      requireReady();
      const { mainView, compareView } = get();
      if (compareView !== null) set({ mainView: compareView, compareView: mainView });
    },

    setSwipe: (position) => set({ swipe: clamp(finite(position, "swipe"), 0, 1) }),

    setOverlayVisible: (id, visible) => {
      const overlay = requireOverlay(id);
      set((state) => ({ overlays: { ...state.overlays, [id]: { ...overlay, visible } } }));
    },

    setOverlayOpacity: (id, opacity) => {
      const overlay = requireOverlay(id);
      const value = clamp(finite(opacity, "opacity"), 0, 1);
      set((state) => ({ overlays: { ...state.overlays, [id]: { ...overlay, opacity: value } } }));
    },

    setSourceFailing: (key, failing) => {
      requireReady();
      if (Boolean(get().failing[key]) === failing) return;
      set((state) => ({ failing: { ...state.failing, [key]: failing } }));
    },

    retrySource: (key) => {
      requireReady();
      if (!get().failing[key]) return;
      set((state) => ({
        failing: { ...state.failing, [key]: false },
        retries: { ...state.retries, [key]: (state.retries[key] ?? 0) + 1 },
      }));
    },

    holdOverlay: (id, held) => {
      if (get().held.includes(id) === held) return;
      set((state) => ({ held: held ? [...state.held, id] : state.held.filter((other) => other !== id) }));
    },

    setSun: (sun) => {
      const current = get().sun;
      set({
        sun: {
          azimuth: sun.azimuth === undefined ? current.azimuth : wrapDegrees(finite(sun.azimuth, "azimuth")),
          altitude:
            sun.altitude === undefined
              ? current.altitude
              : clamp(finite(sun.altitude, "altitude"), LIMITS.sunAltitude.min, LIMITS.sunAltitude.max),
        },
      });
    },

    setHillshadeExaggeration: (value) =>
      set({
        hillshadeExaggeration: clamp(
          finite(value, "exaggeration"),
          LIMITS.hillshadeExaggeration.min,
          LIMITS.hillshadeExaggeration.max,
        ),
      }),

    setTerrainEnabled: (enabled) => {
      const { terrain, camera, cameraRequest } = get();
      if (terrain.enabled === enabled) return;
      // 3D seen from straight above looks flat, so tilt on the way in and
      // level out on the way back.
      const pitch = enabled ? (camera.pitch < 20 ? TERRAIN_PITCH : camera.pitch) : 0;
      set({
        terrain: { ...terrain, enabled },
        camera: { ...camera, pitch },
        cameraRequest: cameraRequest + 1,
      });
    },

    setTerrainExaggeration: (value) =>
      set((state) => ({
        terrain: {
          ...state.terrain,
          exaggeration: clamp(
            finite(value, "exaggeration"),
            LIMITS.terrainExaggeration.min,
            LIMITS.terrainExaggeration.max,
          ),
        },
      })),

    setShowRuledOut: (show) => set({ showRuledOut: show }),

    setShowRecordCounts: (show) => set({ showRecordCounts: show }),

    setCamera: (camera) => {
      const current = get().camera;
      if (
        current.lng === camera.lng &&
        current.lat === camera.lat &&
        current.zoom === camera.zoom &&
        current.bearing === camera.bearing &&
        current.pitch === camera.pitch
      ) {
        return;
      }
      set({ camera });
    },

    requestCamera: (camera) =>
      set((state) => ({ camera: { ...state.camera, ...camera }, cameraRequest: state.cameraRequest + 1 })),

    zoomBy: (levels) => {
      const { camera, requestCamera } = get();
      const zoom = clamp(camera.zoom + finite(levels, "zoom change"), LIMITS.zoom.min, LIMITS.zoom.max);
      if (zoom !== camera.zoom) requestCamera({ zoom });
    },

    resetNorth: () => {
      const { camera, requestCamera } = get();
      if (camera.bearing !== 0) requestCamera({ bearing: 0 });
    },
  };
});

/** The slice of the store that the permalink carries. */
export function selectPermalinkState(state: MapState): PermalinkState {
  return Object.fromEntries(PERMALINK_KEYS.map((key) => [key, state[key]])) as unknown as PermalinkState;
}

/** True when any of these fields differs between two snapshots of a store. Fields compare by identity. */
export function changedAny<T>(next: T, previous: T, keys: ReadonlyArray<keyof T>): boolean {
  return keys.some((key) => next[key] !== previous[key]);
}

/** Pointer position for the status readout, kept apart so it can update often. */
export interface PointerState {
  position: { lng: number; lat: number } | null;
  setPosition: (position: { lng: number; lat: number } | null) => void;
}

export const usePointerStore = create<PointerState>()((set) => ({
  position: null,
  setPosition: (position) => set({ position }),
}));

/**
 * The area the main map shows, for asking the server what is in view. Kept
 * apart from the camera because it also depends on the size of the window.
 * Written by the main pane when it comes to rest.
 */
export interface ViewAreaState {
  /** West, south, east, north in degrees. Null until the map has been drawn. */
  bounds: [number, number, number, number] | null;
  zoom: number;
  setArea: (bounds: [number, number, number, number], zoom: number) => void;
}

export const useViewAreaStore = create<ViewAreaState>()((set, get) => ({
  bounds: null,
  zoom: 0,
  setArea: (bounds, zoom) => {
    const current = get();
    if (current.zoom === zoom && current.bounds?.every((value, i) => value === bounds[i])) return;
    set({ bounds, zoom });
  },
}));
