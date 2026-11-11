/** Addresses of the records feature's panels. */

export const RECORD_SEARCH_PATH = "/records";
export const ELSEWHERE_PATH = "/elsewhere";

export function recordPath(id: number | string): string {
  return `/r/${id}`;
}

/** The "open elsewhere" panel for a spot, to five decimal places (about a metre). */
export function elsewherePath(lon: number, lat: number): string {
  return `${ELSEWHERE_PATH}?lon=${lon.toFixed(5)}&lat=${lat.toFixed(5)}`;
}
