import { apiFetch } from "../../../api/client.js";
import type { components, operations } from "../../../api/schema.js";
import { type LngLat, lineLengthM, sampleCount } from "./line.js";

/** `POST /terrain/profile`, as the generated schema has it. */
export type ProfileOut = operations["terrain_profile"]["responses"][200]["content"]["application/json"];
export type ProfileSample = components["schemas"]["ProfileSample"];
type ProfileRequest = components["schemas"]["ProfileRequest"];

export function fetchProfile(points: readonly LngLat[], signal?: AbortSignal): Promise<ProfileOut> {
  if (points.length < 2) throw new Error("A profile needs at least two points");
  const body: ProfileRequest = {
    line: { type: "LineString", coordinates: points.map(([lng, lat]): [number, number] => [lng, lat]) },
    samples: sampleCount(lineLengthM(points)),
  };
  return apiFetch<ProfileOut>("/terrain/profile", { method: "POST", body, signal });
}
