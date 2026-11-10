import { keepPreviousData } from "@tanstack/react-query";
import { isEndpointMissing, isTransient } from "../../api/client.js";
import { useOptionalEndpointQuery } from "../../api/useOptionalEndpointQuery.js";
import { useDebounced } from "../../ui/useDebounced.js";
import { type Bbox, bboxParam, fetchFindingsInBox, snapBbox } from "./api.js";
import { type FindingCollection, NO_FINDINGS } from "./types.js";

/** How long the map must hold still before the findings in view are asked for. */
export const FINDINGS_DEBOUNCE_MS = 300;
/** How long an answer is used before the same box is asked for again. */
export const FINDINGS_STALE_MS = 30_000;

export interface FindingsInBox {
  /** What to draw. Empty until the first answer, and kept from the last box while the next is on its way. */
  findings: FindingCollection;
  /** True once the server has said it has no findings endpoint. Nothing more is asked of it. */
  missing: boolean;
  /** The last failure other than a missing endpoint, after its one retry, or null. */
  error: Error | null;
  /** Changes each time a request fails for good, so a caller can react to each failure once. */
  errorAt: number;
}

/**
 * The findings inside `bbox`, from `GET /findings?bbox=&format=geojson`.
 *
 * A box given at mount is asked for at once. After that the box is taken
 * once it has held still for `FINDINGS_DEBOUNCE_MS`, so a drag asks once at
 * the end and not on every frame. A request still in flight is cancelled
 * when the box changes or the caller unmounts. Pass null to ask for nothing,
 * for example while the overlay is off.
 *
 * `attempt` is part of the cache key. Raising it asks for the same box
 * afresh, which is how a person's "Try again" gets past a failure.
 *
 * A server without the endpoint (404, 405 or 501) is remembered for the life
 * of the page and never asked again. Other failures are retried once if they
 * may pass, then reported through `error`.
 */
export function useFindingsInBox(bbox: Bbox | null, attempt = 0): FindingsInBox {
  // Debounced as text, because a caller hands over a new array on every render.
  const settled = useDebounced(bbox === null ? null : bboxParam(snapBbox(bbox)), FINDINGS_DEBOUNCE_MS);

  const { query, missing } = useOptionalEndpointQuery({
    queryKey: ["findings", "bbox", settled, attempt],
    queryFn: async ({ signal }) => {
      if (settled === null) throw new Error("useFindingsInBox ran with no box");
      return fetchFindingsInBox(settled.split(",").map(Number) as Bbox, signal);
    },
    enabled: settled !== null,
    staleTime: FINDINGS_STALE_MS,
    placeholderData: keepPreviousData,
    retry: (failureCount, error) => failureCount < 1 && isTransient(error),
  });

  const failed = query.isError && !isEndpointMissing(query.error);
  return {
    findings: missing || bbox === null ? NO_FINDINGS : (query.data ?? NO_FINDINGS),
    missing,
    error: failed ? query.error : null,
    errorAt: failed ? query.errorUpdatedAt : 0,
  };
}
