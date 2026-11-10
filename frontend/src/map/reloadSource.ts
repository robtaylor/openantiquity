/**
 * Fetching a map source again after it has failed.
 *
 * Raster and elevation sources have their tiles reloaded with the public
 * `map.refreshTiles`. MapLibre 5 marked a failed tile "expired" there, which
 * counts as drawable, and its raster and hillshade painters then threw on
 * the missing texture every frame until the second fetch answered. From
 * 6.1.0 a failed tile goes back to "loading", which is not drawn.
 *
 * Vector sources still cannot use the public calls, as of MapLibre 6.17.0.
 * The same reload puts a failed vector tile back to "loading", and the
 * vector source then waits for a reply to a request it never sends
 * (`VectorTileSource.loadTile` returns a promise for a tile that already has
 * a worker and is "loading"). The tile is never fetched again. `setUrl`
 * reaches the same reload. So a vector source's tiles are dropped instead,
 * and the map makes new ones on its next look. That takes two members
 * MapLibre does not document, `style.tileManagers[id].clearTiles` and
 * `map._update`, so both are checked for. If either has gone, the public
 * calls stand in and a failing vector layer will not be fetched again.
 *
 * A source declared by the address of a TileJSON is also given that address
 * again, which is the only thing that makes MapLibre fetch the TileJSON a
 * second time.
 *
 * The resilience end-to-end tests cover raster, elevation and vector layers.
 */

/** The slice of a MapLibre map that reloading needs, including the two undocumented parts. */
export interface ReloadableMap {
  getSource(id: string): unknown;
  refreshTiles(sourceId: string): unknown;
}

/** What reloading needs to know of the source's declaration in the style. */
export interface SourceDeclaration {
  type: string;
  url?: string | undefined;
}

interface TileManagerLike {
  clearTiles?: () => void;
}

interface MapInternals {
  style?: { tileManagers?: Record<string, TileManagerLike | undefined> };
  /** Marks the map's sources as needing another look, and asks for a frame. */
  _update?: (updateStyle?: boolean) => unknown;
}

interface UrlSource {
  setUrl?: (url: string) => unknown;
}

/** Drop a source's tiles so the map makes new ones. False if MapLibre no longer has the parts this needs. */
function dropTiles(map: ReloadableMap, sourceId: string): boolean {
  const internals = map as unknown as MapInternals;
  const manager = internals.style?.tileManagers?.[sourceId];
  if (typeof manager?.clearTiles !== "function" || typeof internals._update !== "function") return false;
  manager.clearTiles();
  internals._update(false);
  return true;
}

/** Fetch `sourceId` again. Does nothing if the map has no such source. */
export function reloadSource(map: ReloadableMap, sourceId: string, declaration: SourceDeclaration): void {
  const source = map.getSource(sourceId) as UrlSource | undefined;
  if (!source) return;
  const dropped = declaration.type === "vector" && dropTiles(map, sourceId);
  if (declaration.url !== undefined && typeof source.setUrl === "function") {
    source.setUrl(declaration.url);
    return;
  }
  if (!dropped) map.refreshTiles(sourceId);
}
