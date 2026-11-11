/**
 * One tile from a layer's own address template, for the small previews in the
 * layer panel. The template comes from /meta with its version token, exactly
 * as the map uses it: nothing here makes up an address.
 */

export class TileTemplateError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TileTemplateError";
  }
}

export interface TileCoord {
  z: number;
  x: number;
  y: number;
}

/** Half the circumference of the Web Mercator world, in metres. */
const HALF_WORLD = 20037508.342789244;

/** The tile at zoom `z` that holds a point, and where in it the point falls, from 0 to 1 across and down. */
export function tileAt(lng: number, lat: number, z: number): TileCoord & { fx: number; fy: number } {
  if (!Number.isInteger(z) || z < 0) throw new TileTemplateError(`Zoom must be a whole number, got ${z}`);
  const n = 2 ** z;
  const sin = Math.sin((lat * Math.PI) / 180);
  const worldX = ((lng + 180) / 360) * n;
  const worldY = (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * n;
  const x = Math.min(n - 1, Math.max(0, Math.floor(worldX)));
  const y = Math.min(n - 1, Math.max(0, Math.floor(worldY)));
  return { z, x, y, fx: worldX - x, fy: worldY - y };
}

/** The tile's Web Mercator bounds as "minx,miny,maxx,maxy", as MapLibre fills `{bbox-epsg-3857}`. */
function bbox3857({ z, x, y }: TileCoord): string {
  const size = (2 * HALF_WORLD) / 2 ** z;
  const minX = -HALF_WORLD + x * size;
  const maxY = HALF_WORLD - y * size;
  return [minX, maxY - size, minX + size, maxY].join(",");
}

function quadkey({ z, x, y }: TileCoord): string {
  let key = "";
  for (let level = z; level > 0; level--) {
    const mask = 1 << (level - 1);
    key += String((x & mask ? 1 : 0) + (y & mask ? 2 : 0));
  }
  return key;
}

/**
 * Fill a tile address template the way MapLibre does: `{z}`, `{x}`, `{y}`,
 * `{bbox-epsg-3857}`, `{quadkey}`, `{ratio}` (standard resolution) and
 * `{prefix}`. Anything else in braces is a template this code can't fill.
 */
export function fillTileTemplate(template: string, tile: TileCoord): string {
  const values: Record<string, string> = {
    z: String(tile.z),
    x: String(tile.x),
    y: String(tile.y),
    "bbox-epsg-3857": bbox3857(tile),
    quadkey: quadkey(tile),
    ratio: "",
    prefix: ((tile.x % 16).toString(16) + (tile.y % 16).toString(16)).toLowerCase(),
  };
  return template.replace(/\{([^{}]+)\}/g, (match, name: string) => {
    const value = values[name];
    if (value === undefined) throw new TileTemplateError(`The tile address ${template} has an unknown part ${match}`);
    return value;
  });
}

/** As `fillTileTemplate`, but null for a template it can't fill, such as one using `{s}` or `{-y}`. */
export function tileUrlOrNull(template: string, tile: TileCoord): string | null {
  try {
    return fillTileTemplate(template, tile);
  } catch (error) {
    if (error instanceof TileTemplateError) return null;
    throw error;
  }
}
