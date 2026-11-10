export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/** Wrap an angle into [0, 360). */
export function wrapDegrees(value: number): number {
  return ((value % 360) + 360) % 360;
}

/** An angle rounded to a whole degree in [0, 360), so 359.6 comes out as 0, not 360. */
export function roundDegrees(value: number): number {
  return wrapDegrees(Math.round(value));
}
