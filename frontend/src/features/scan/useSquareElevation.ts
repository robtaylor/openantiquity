import { useQuery } from "@tanstack/react-query";
import { isTransient } from "../../api/client.js";
import { coverageBox, fetchCoverage, insideRing } from "../layers/coverage/coverage.js";
import { terrainKeys } from "../layers/keys.js";
import type { Square } from "./api.js";

/**
 * Whether one-metre elevation covers the middle of the square, from the
 * same `GET /terrain/coverage` the map's coverage shading asks, so the two
 * share an answer. The server offers only squares with elevation, but its
 * catalogue lists whole tiles at the coast and the borders, and the data
 * can change after a square was handed out. "unknown" until the answer is in,
 * and when it can't be had: the square is then offered as usual.
 */
export function useSquareElevation(square: Square): "yes" | "no" | "unknown" {
  const box = coverageBox(square.bbox);
  const query = useQuery({
    queryKey: terrainKeys.coverage(box),
    queryFn: ({ signal }) => fetchCoverage(box, signal),
    staleTime: 60 * 60_000,
    retry: (failures, error) => failures < 1 && isTransient(error),
  });
  if (!query.data) return "unknown";
  return query.data.some((tile) => insideRing(square.centre, tile.ring)) ? "yes" : "no";
}
