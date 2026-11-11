import type { LngLat } from "./profile/line.js";

/** Query keys for the terrain tools. Nothing else builds one. */
export const terrainKeys = {
  all: ["terrain"] as const,
  profile: (points: readonly LngLat[]) => ["terrain", "profile", points.flat()] as const,
  allCoverage: ["terrain", "coverage"] as const,
  coverage: (bbox: readonly number[]) => ["terrain", "coverage", ...bbox] as const,
};
