/**
 * Keys under which the map store keeps the loading trouble of each source:
 * an overlay, a view, or the elevation data.
 */

const OVERLAY_PREFIX = "overlay:";

export function overlayTroubleKey(overlayId: string): string {
  return `${OVERLAY_PREFIX}${overlayId}`;
}

export function isOverlayTroubleKey(key: string): boolean {
  return key.startsWith(OVERLAY_PREFIX);
}

export function viewTroubleKey(viewId: string): string {
  return `view:${viewId}`;
}

export const DEM_TROUBLE_KEY = "dem";
