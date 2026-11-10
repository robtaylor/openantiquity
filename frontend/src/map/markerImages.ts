/**
 * Marker images built in code, so the map needs no sprite sheet.
 *
 * MapLibre can recolour and outline an image at draw time if it is a signed
 * distance field: the alpha channel holds the distance to the shape's edge,
 * with 0.75 on the edge itself and eight pixels of distance to one unit.
 */

import { clamp } from "../ui/math.js";

export interface RawImage {
  width: number;
  height: number;
  data: Uint8Array;
}

const SDF_EDGE = 0.75;
const SDF_RADIUS = 8;

/** Extra options `map.addImage` needs for the images made here. */
export const SDF_IMAGE_OPTIONS = { sdf: true, pixelRatio: 2 } as const;

/** Width and height of the square image, in image pixels. */
const SQUARE_IMAGE_SIZE = 32;
/** Side of the square drawn in it. At `pixelRatio: 2` it is eight CSS pixels across, with room around it for a halo. */
const SQUARE_SIDE = 16;

/** A filled square as a signed distance field. */
export function squareSdf(): RawImage {
  const size = SQUARE_IMAGE_SIZE;
  const side = SQUARE_SIDE;
  const data = new Uint8Array(size * size * 4);
  const half = side / 2;
  const centre = size / 2;
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const dx = Math.abs(x + 0.5 - centre) - half;
      const dy = Math.abs(y + 0.5 - centre) - half;
      // Signed distance to the square: negative inside, positive outside.
      const outside = Math.hypot(Math.max(dx, 0), Math.max(dy, 0));
      const inside = Math.min(Math.max(dx, dy), 0);
      const alpha = SDF_EDGE - (outside + inside) / SDF_RADIUS;
      data[(y * size + x) * 4 + 3] = Math.round(clamp(alpha, 0, 1) * 255);
    }
  }
  return { width: size, height: size, data };
}
