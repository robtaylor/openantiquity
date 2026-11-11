/**
 * A small hillshade drawn from elevation pixels, for the raking light's
 * preview in the layer panel. The map draws the real thing with MapLibre;
 * this only has to look like it.
 */

/** Terrarium encoding: height in metres is red × 256 + green + blue ÷ 256 − 32768. */
export function terrariumHeights(rgba: Uint8ClampedArray, width: number, height: number): Float32Array {
  if (rgba.length !== width * height * 4) throw new Error(`Expected ${width * height * 4} bytes, got ${rgba.length}`);
  const heights = new Float32Array(width * height);
  for (let i = 0; i < heights.length; i++) {
    const r = rgba[i * 4] ?? 0;
    const g = rgba[i * 4 + 1] ?? 0;
    const b = rgba[i * 4 + 2] ?? 0;
    heights[i] = r * 256 + g + b / 256 - 32768;
  }
  return heights;
}

export interface Light {
  /** Degrees clockwise from north. */
  azimuth: number;
  /** Degrees above the horizon. */
  altitude: number;
  /** Vertical exaggeration. */
  exaggeration: number;
}

/**
 * Grey levels, 0 to 255, for a grid of heights `cellSize` metres apart, lit
 * from `light`. Level ground comes out mid-grey whatever the sun's height, so
 * a lower sun raises contrast without darkening everything. The map does the
 * same only between about 15 and 48 degrees (see `rakingBaseGrey` in
 * style.ts); above that it drifts lighter, which this preview doesn't show.
 * Slopes use Horn's method, and edge cells reuse their neighbours.
 */
export function hillshade(
  heights: Float32Array,
  width: number,
  height: number,
  cellSize: number,
  light: Light,
): Uint8ClampedArray {
  if (heights.length !== width * height) throw new Error("hillshade: the grid and its size disagree");
  if (!(cellSize > 0)) throw new Error("hillshade: the cell size must be positive");
  const zenith = ((90 - light.altitude) * Math.PI) / 180;
  // Aspect is measured counter-clockwise from east, so turn the compass bearing into the same terms.
  const azimuth = ((360 - light.azimuth + 90) * Math.PI) / 180;
  const flat = Math.cos(zenith);
  const span = Math.max(flat, 1 - flat);
  const at = (x: number, y: number): number => {
    const cx = Math.min(width - 1, Math.max(0, x));
    const cy = Math.min(height - 1, Math.max(0, y));
    return (heights[cy * width + cx] ?? 0) * light.exaggeration;
  };
  const out = new Uint8ClampedArray(width * height);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const dzdx =
        (at(x + 1, y - 1) +
          2 * at(x + 1, y) +
          at(x + 1, y + 1) -
          (at(x - 1, y - 1) + 2 * at(x - 1, y) + at(x - 1, y + 1))) /
        (8 * cellSize);
      // Rows run southwards, so north is up the grid.
      const dzdy =
        (at(x - 1, y - 1) +
          2 * at(x, y - 1) +
          at(x + 1, y - 1) -
          (at(x - 1, y + 1) + 2 * at(x, y + 1) + at(x + 1, y + 1))) /
        (8 * cellSize);
      const slope = Math.atan(Math.hypot(dzdx, dzdy));
      // The way the ground falls, counter-clockwise from east.
      const aspect = Math.atan2(-dzdy, -dzdx);
      const shade =
        Math.cos(zenith) * Math.cos(slope) + Math.sin(zenith) * Math.sin(slope) * Math.cos(azimuth - aspect);
      out[y * width + x] = Math.round((0.5 + (0.5 * (shade - flat)) / span) * 255);
    }
  }
  return out;
}
