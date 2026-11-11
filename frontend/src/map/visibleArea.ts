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
 * Where a north-up camera must point, at `zoom`, for `lng`/`lat` to fall in
 * the middle of the uncovered map. MapLibre draws 512 px a tile.
 */
export function centreForVisible(
  lng: number,
  lat: number,
  zoom: number,
  cover: MapCover,
): { lng: number; lat: number } {
  const offset = visibleOffset(cover);
  const worldPx = 512 * 2 ** zoom;
  return {
    lng: lng - (offset.x / worldPx) * 360,
    lat: latitudeOf(mercatorY(lat) + (offset.y / worldPx) * 2 * Math.PI),
  };
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
