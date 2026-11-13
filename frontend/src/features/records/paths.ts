/** Addresses of the records feature's panels. */

export const RECORD_SEARCH_PATH = "/records";
export const ELSEWHERE_PATH = "/elsewhere";

/** A record's page. The id is encoded, so an id from elsewhere can never name another address. */
export function recordPath(id: number | string): string {
  return `/r/${encodeURIComponent(String(id))}`;
}

/** The "open elsewhere" panel for a spot, to five decimal places (about a metre). */
export function elsewherePath(lon: number, lat: number): string {
  return `${ELSEWHERE_PATH}?lon=${lon.toFixed(5)}&lat=${lat.toFixed(5)}`;
}

/**
 * What a record's page is told when a click on the map opened it. The page
 * then leaves the map where it is, where it would otherwise go to the
 * record's middle, which for a large record can be far from the click.
 */
export const OPENED_FROM_MAP = { openedFromMap: true } as const;

/** Whether this is the state `OPENED_FROM_MAP` puts on a page's address. */
export function wasOpenedFromMap(state: unknown): boolean {
  return typeof state === "object" && state !== null && (state as { openedFromMap?: unknown }).openedFromMap === true;
}
