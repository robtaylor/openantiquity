import { create } from "zustand";

/**
 * How much of each edge of the map the shell's chrome covers, in pixels: the
 * rail and the side panel on a desktop; the search field, the sheet, the
 * status bar and the tab bar on a phone. The map itself fills the window, so
 * its middle is under the panel or the sheet. Anything that means "the middle
 * of what you can see", such as the height profile's cross, uses these.
 */
export interface MapCover {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

export const NO_COVER: MapCover = { left: 0, right: 0, top: 0, bottom: 0 };

interface MapCoverState {
  cover: MapCover;
  setCover: (cover: MapCover) => void;
}

export const useMapCover = create<MapCoverState>()((set, get) => ({
  cover: NO_COVER,
  setCover: (cover) => {
    const current = get().cover;
    if (
      current.left === cover.left &&
      current.right === cover.right &&
      current.top === cover.top &&
      current.bottom === cover.bottom
    ) {
      return;
    }
    set({ cover });
  },
}));

/** How far the middle of the uncovered map lies from the middle of the whole map, in pixels, right and down. */
export function visibleOffset(cover: MapCover): { x: number; y: number } {
  return { x: (cover.left - cover.right) / 2, y: (cover.top - cover.bottom) / 2 };
}

/** Web Mercator y, as a fraction of the world's height per 2π. */
function mercatorY(lat: number): number {
  return Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));
}

function latitudeOf(y: number): number {
  return ((2 * Math.atan(Math.exp(y)) - Math.PI / 2) * 180) / Math.PI;
}

/**
 * The part of a north-up view's bounds that is not covered, given the map's
 * size in pixels. Longitude is linear across the screen and latitude linear in
 * Mercator y, so both are exact for a flat, north-up map.
 */
export function uncoveredBounds(
  bounds: readonly [number, number, number, number],
  size: { width: number; height: number },
  cover: MapCover,
): [number, number, number, number] {
  const [west, south, east, north] = bounds;
  const across = (east - west) / Math.max(1, size.width);
  const top = mercatorY(north);
  const down = (top - mercatorY(south)) / Math.max(1, size.height);
  return [
    west + cover.left * across,
    latitudeOf(top - (size.height - cover.bottom) * down),
    east - cover.right * across,
    latitudeOf(top - cover.top * down),
  ];
}

/**
 * Where a camera must point, at `zoom` and `bearing`, for `lng`/`lat` to fall
 * in the middle of the uncovered map. MapLibre draws 512 px a tile. The
 * screen offset is turned by the bearing onto the ground, and is exact for a
 * north-up map.
 */
export function centreForVisible(
  lng: number,
  lat: number,
  zoom: number,
  cover: MapCover,
  bearing = 0,
): { lng: number; lat: number } {
  const offset = visibleOffset(cover);
  const angle = (bearing * Math.PI) / 180;
  const east = bearing === 0 ? offset.x : offset.x * Math.cos(angle) - offset.y * Math.sin(angle);
  const south = bearing === 0 ? offset.y : offset.x * Math.sin(angle) + offset.y * Math.cos(angle);
  const worldPx = 512 * 2 ** zoom;
  return {
    lng: lng - (east / worldPx) * 360,
    lat: latitudeOf(mercatorY(lat) + (south / worldPx) * 2 * Math.PI),
  };
}

export interface FramingOptions {
  /** How much of the uncovered width and height the points may take, from 0 to 1. */
  fill?: number;
  /** Pixels kept clear on every side of the uncovered map, inside `fill`. */
  margin?: number;
  /** The closest the camera comes, which is also the zoom for a single point. */
  maxZoom: number;
  /** The bearing the camera keeps. The points' extent is measured as if the map faced north. */
  bearing?: number;
}

/**
 * Where to point the camera, and how close, so every point is in the part of
 * a `size` map that `cover` leaves showing: their middle in the middle of
 * it, and their extent taking `fill` of what is left once `margin` is kept
 * on every side. Null for no points.
 */
export function framePoints(
  points: ReadonlyArray<readonly [number, number]>,
  size: { width: number; height: number },
  cover: MapCover,
  { fill = 1, margin = 0, maxZoom, bearing = 0 }: FramingOptions,
): { lng: number; lat: number; zoom: number } | null {
  if (points.length === 0) return null;
  const lngs = points.map((point) => point[0]);
  const lats = points.map((point) => point[1]);
  const west = Math.min(...lngs);
  const east = Math.max(...lngs);
  const south = Math.min(...lats);
  const north = Math.max(...lats);
  // The points' extent in pixels at zoom 0, 512 px a tile, in Web Mercator as the map draws it.
  const across = ((east - west) / 360) * 512;
  const down = ((mercatorY(north) - mercatorY(south)) / (2 * Math.PI)) * 512;
  const width = size.width - cover.left - cover.right - margin * 2;
  const height = size.height - cover.top - cover.bottom - margin * 2;
  const zoomToFit = (pixels: number, span: number): number =>
    span > 0 ? Math.log2((Math.max(1, pixels) * fill) / span) : maxZoom;
  const zoom = Math.max(0, Math.min(maxZoom, zoomToFit(width, across), zoomToFit(height, down)));
  return { ...centreForVisible((west + east) / 2, (south + north) / 2, zoom, cover, bearing), zoom };
}

/**
 * The ground at the middle of the uncovered map, for a camera that points at
 * `lng`/`lat`: what "the middle of the map" means to someone looking at it,
 * with the panel or the sheet over part of it. It turns the screen offset by
 * the bearing, and takes the map as flat, as a tilted map's middle is near
 * enough for a readout. The inverse of `centreForVisible` for a north-up map.
 */
export function visibleCentre(
  camera: { lng: number; lat: number; zoom: number; bearing?: number },
  cover: MapCover,
): { lng: number; lat: number } {
  const offset = visibleOffset(cover);
  if (offset.x === 0 && offset.y === 0) return { lng: camera.lng, lat: camera.lat };
  const bearing = ((camera.bearing ?? 0) * Math.PI) / 180;
  const east = offset.x * Math.cos(bearing) - offset.y * Math.sin(bearing);
  const south = offset.x * Math.sin(bearing) + offset.y * Math.cos(bearing);
  const worldPx = 512 * 2 ** camera.zoom;
  return {
    lng: camera.lng + (east / worldPx) * 360,
    lat: latitudeOf(mercatorY(camera.lat) - (south / worldPx) * 2 * Math.PI),
  };
}
