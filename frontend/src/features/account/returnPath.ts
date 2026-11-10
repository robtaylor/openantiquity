/**
 * `returnPath(location)`: the `next` that brings someone back to exactly what
 * they are looking at now. Pass the router's location. The map position in
 * the address trails the map by a moment, and changes without the router
 * hearing of it (see `usePermalink`), so it is read from the map itself.
 */

import { encodePermalink } from "../../map/permalink.js";
import { selectPermalinkState, useMapStore } from "../../map/store.js";
import { nextFromLocation, type PathParts } from "./next.js";

/** The map's position as an address fragment, or `fallback` before the map has started. */
export function currentMapHash(fallback: string): string {
  const map = useMapStore.getState();
  return map.meta === null ? fallback : encodePermalink(selectPermalinkState(map));
}

export function returnPath(location: PathParts): string {
  return nextFromLocation({ ...location, hash: currentMapHash(location.hash) });
}
