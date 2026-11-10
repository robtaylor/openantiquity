/**
 * Permalinks. The URL hash carries everything needed to reopen a view
 * exactly: camera, main and comparison layers, sun position, relief
 * strength, 3D and overlay state.
 *
 *   #m=14/51.4286/-1.8542/0/0&v=composite&c=slope&s=315/35&x=0.5&t=1/1.5&o=osm:80,findings:100,records:100:h
 *
 *   m  zoom/latitude/longitude/bearing/pitch
 *   v  main view id
 *   c  comparison view id (absent when not comparing)
 *   s  sun azimuth/altitude in degrees
 *   x  raking light relief, as a vertical exaggeration
 *   t  3D on (1) or off (0), then terrain exaggeration
 *   o  overlays as id:opacity-per-cent, with ":h" appended when hidden
 *   r  present (1) when ruled-out findings are shown
 */

import { clamp, roundDegrees, wrapDegrees } from "../ui/math.js";

export interface CameraState {
  lng: number;
  lat: number;
  zoom: number;
  bearing: number;
  pitch: number;
}

export interface SunState {
  /** Degrees clockwise from north, 0 to 359. */
  azimuth: number;
  /** Degrees above the horizon. */
  altitude: number;
}

export interface TerrainState {
  enabled: boolean;
  exaggeration: number;
}

export interface OverlayState {
  visible: boolean;
  /** 0 to 1. */
  opacity: number;
}

export interface PermalinkState {
  camera: CameraState;
  mainView: string;
  compareView: string | null;
  sun: SunState;
  hillshadeExaggeration: number;
  terrain: TerrainState;
  overlays: Record<string, OverlayState>;
  showRuledOut: boolean;
}

/** Every field of `PermalinkState`, so code that walks the fields cannot miss one. */
const PERMALINK_FIELDS: Record<keyof PermalinkState, true> = {
  camera: true,
  mainView: true,
  compareView: true,
  sun: true,
  hillshadeExaggeration: true,
  terrain: true,
  overlays: true,
  showRuledOut: true,
};

export const PERMALINK_KEYS = Object.keys(PERMALINK_FIELDS) as ReadonlyArray<keyof PermalinkState>;

export const LIMITS = {
  /** The map is created with these limits too, so a link can never ask for a zoom the map cannot show. */
  zoom: { min: 0, max: 20 },
  pitch: { min: 0, max: 75 },
  sunAltitude: { min: 5, max: 70 },
  /**
   * Vertical exaggeration of the raking light relief. 1 is true to life where
   * the elevation tiles are zoom 15 or deeper. MapLibre steepens shallower
   * ones: see `HILLSHADE_DEM_SCALE` in style.ts.
   */
  hillshadeExaggeration: { min: 0.5, max: 10 },
  terrainExaggeration: { min: 0.5, max: 5 },
} as const;

export { clamp, wrapDegrees };

function round(value: number, places: number): number {
  const factor = 10 ** places;
  const rounded = Math.round(value * factor) / factor;
  // Avoid "-0" in the URL.
  return rounded === 0 ? 0 : rounded;
}

/** Wrap a bearing into (-180, 180], the range MapLibre reports. */
function wrapBearing(value: number): number {
  const wrapped = wrapDegrees(value);
  return wrapped > 180 ? wrapped - 360 : wrapped;
}

/** Round every number to the precision the hash carries. */
export function normalisePermalinkState(state: PermalinkState): PermalinkState {
  const overlays: Record<string, OverlayState> = {};
  for (const [id, overlay] of Object.entries(state.overlays)) {
    overlays[id] = { visible: overlay.visible, opacity: round(clamp(overlay.opacity, 0, 1), 2) };
  }
  return {
    camera: {
      lng: round(state.camera.lng, 5),
      lat: round(state.camera.lat, 5),
      zoom: round(clamp(state.camera.zoom, LIMITS.zoom.min, LIMITS.zoom.max), 2),
      bearing: round(wrapBearing(state.camera.bearing), 1),
      pitch: round(clamp(state.camera.pitch, LIMITS.pitch.min, LIMITS.pitch.max), 1),
    },
    mainView: state.mainView,
    compareView: state.compareView,
    sun: {
      azimuth: roundDegrees(state.sun.azimuth),
      altitude: Math.round(clamp(state.sun.altitude, LIMITS.sunAltitude.min, LIMITS.sunAltitude.max)),
    },
    hillshadeExaggeration: round(
      clamp(state.hillshadeExaggeration, LIMITS.hillshadeExaggeration.min, LIMITS.hillshadeExaggeration.max),
      2,
    ),
    terrain: {
      enabled: state.terrain.enabled,
      exaggeration: round(
        clamp(state.terrain.exaggeration, LIMITS.terrainExaggeration.min, LIMITS.terrainExaggeration.max),
        2,
      ),
    },
    overlays,
    showRuledOut: state.showRuledOut,
  };
}

/** Encode the state as a URL hash, including the leading "#". */
export function encodePermalink(state: PermalinkState): string {
  const s = normalisePermalinkState(state);
  const parts = [
    `m=${s.camera.zoom}/${s.camera.lat}/${s.camera.lng}/${s.camera.bearing}/${s.camera.pitch}`,
    `v=${encodeURIComponent(s.mainView)}`,
  ];
  if (s.compareView !== null) parts.push(`c=${encodeURIComponent(s.compareView)}`);
  parts.push(`s=${s.sun.azimuth}/${s.sun.altitude}`);
  parts.push(`x=${s.hillshadeExaggeration}`);
  parts.push(`t=${s.terrain.enabled ? 1 : 0}/${s.terrain.exaggeration}`);
  const overlays = Object.entries(s.overlays).map(
    ([id, overlay]) => `${encodeURIComponent(id)}:${Math.round(overlay.opacity * 100)}${overlay.visible ? "" : ":h"}`,
  );
  if (overlays.length > 0) parts.push(`o=${overlays.join(",")}`);
  if (s.showRuledOut) parts.push("r=1");
  return `#${parts.join("&")}`;
}

function numbers(value: string, count: number): number[] | null {
  const pieces = value.split("/");
  if (pieces.length !== count) return null;
  const parsed = pieces.map((piece) => (piece.trim() === "" ? Number.NaN : Number(piece)));
  return parsed.every((n) => Number.isFinite(n)) ? parsed : null;
}

function decodeId(value: string): string | null {
  try {
    const id = decodeURIComponent(value);
    return id === "" ? null : id;
  } catch {
    return null;
  }
}

/**
 * Decode a URL hash. Anything missing or malformed is left out of the result,
 * so a damaged link restores what it can and falls back to defaults for the
 * rest. Ids are not checked here: the store drops ones the catalogue lacks.
 */
export function decodePermalink(hash: string): Partial<PermalinkState> {
  const result: Partial<PermalinkState> = {};
  const body = hash.startsWith("#") ? hash.slice(1) : hash;
  if (body === "") return result;

  const fields = new Map<string, string>();
  for (const part of body.split("&")) {
    const split = part.indexOf("=");
    if (split > 0) fields.set(part.slice(0, split), part.slice(split + 1));
  }

  const m = fields.get("m");
  const camera = m === undefined ? null : numbers(m, 5);
  if (camera) {
    const [zoom, lat, lng, bearing, pitch] = camera as [number, number, number, number, number];
    if (Math.abs(lat) <= 90 && Math.abs(lng) <= 180) {
      result.camera = {
        zoom: clamp(zoom, LIMITS.zoom.min, LIMITS.zoom.max),
        lat,
        lng,
        bearing: wrapBearing(bearing),
        pitch: clamp(pitch, LIMITS.pitch.min, LIMITS.pitch.max),
      };
    }
  }

  const v = fields.get("v");
  const mainView = v === undefined ? null : decodeId(v);
  if (mainView !== null) result.mainView = mainView;

  if (mainView !== null || camera) {
    // A link that names a view also fixes whether a comparison is open.
    const c = fields.get("c");
    result.compareView = c === undefined ? null : decodeId(c);
  }

  const s = fields.get("s");
  const sun = s === undefined ? null : numbers(s, 2);
  if (sun) {
    const [azimuth, altitude] = sun as [number, number];
    result.sun = {
      azimuth: roundDegrees(azimuth),
      altitude: clamp(altitude, LIMITS.sunAltitude.min, LIMITS.sunAltitude.max),
    };
  }

  const x = fields.get("x");
  if (x !== undefined && x !== "" && Number.isFinite(Number(x))) {
    result.hillshadeExaggeration = clamp(Number(x), LIMITS.hillshadeExaggeration.min, LIMITS.hillshadeExaggeration.max);
  }

  const t = fields.get("t");
  const terrain = t === undefined ? null : numbers(t, 2);
  if (terrain) {
    const [enabled, exaggeration] = terrain as [number, number];
    result.terrain = {
      enabled: enabled === 1,
      exaggeration: clamp(exaggeration, LIMITS.terrainExaggeration.min, LIMITS.terrainExaggeration.max),
    };
  }

  const o = fields.get("o");
  if (o !== undefined && o !== "") {
    const overlays: Record<string, OverlayState> = {};
    for (const entry of o.split(",")) {
      const [rawId, rawOpacity, flag] = entry.split(":");
      const id = rawId === undefined ? null : decodeId(rawId);
      const opacity = rawOpacity === undefined || rawOpacity === "" ? Number.NaN : Number(rawOpacity);
      if (id === null || !Number.isFinite(opacity)) continue;
      overlays[id] = { visible: flag !== "h", opacity: clamp(opacity, 0, 100) / 100 };
    }
    if (Object.keys(overlays).length > 0) result.overlays = overlays;
  }

  if (fields.has("m") || fields.has("v")) result.showRuledOut = fields.get("r") === "1";

  return result;
}
