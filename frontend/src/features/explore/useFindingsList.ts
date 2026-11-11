import { keepPreviousData, useInfiniteQuery } from "@tanstack/react-query";
import { isEndpointMissing, isTransient } from "../../api/client.js";
import { useViewAreaStore } from "../../map/store.js";
import { FINDINGS_MIN_ZOOM } from "../../map/useFindingsOverlay.js";
import { useDebounced } from "../../ui/useDebounced.js";
import { bboxParam, fetchFindingsPage, parseBboxParam, snapBbox } from "../findings/api.js";
import { filtersKey, useEffectiveFilters } from "../findings/filters.js";
import { findingKeys } from "../findings/keys.js";
import type { FindingSummary } from "../findings/types.js";
import { FINDINGS_DEBOUNCE_MS, FINDINGS_STALE_MS } from "../findings/useFindingsInBox.js";

export type FindingsListStatus =
  /** The map is zoomed out too far for findings, as it is for the markers. */
  | "zoomed-out"
  /** The filters leave nothing to ask for. */
  | "filtered-out"
  | "loading"
  | "error"
  /** The server has no findings endpoint yet. */
  | "missing"
  | "ready";

export interface FindingsList {
  status: FindingsListStatus;
  items: FindingSummary[];
  hasMore: boolean;
  loadingMore: boolean;
  /** True while the list shown is for where the map was, and the new place is on its way. */
  stale: boolean;
  error: Error | null;
  loadMore: () => void;
  retry: () => void;
}

/**
 * The findings in view, a page at a time, newest first, for the Explore
 * panel. It asks for exactly the box and filters the map's markers use, so
 * the two agree: the same snapped box, the same wait for the map to hold
 * still, and nothing below the zoom where the markers stop.
 */
export function useFindingsList(): FindingsList {
  const bounds = useViewAreaStore((state) => state.bounds);
  const zoom = useViewAreaStore((state) => state.zoom);
  const zoomedOut = bounds === null || zoom < FINDINGS_MIN_ZOOM;
  const settled = useDebounced(zoomedOut ? null : bboxParam(snapBbox(bounds)), FINDINGS_DEBOUNCE_MS);
  const filters = useEffectiveFilters();

  const query = useInfiniteQuery({
    queryKey: findingKeys.list(settled, filtersKey(filters)),
    queryFn: ({ pageParam, signal }) => {
      if (settled === null) throw new Error("useFindingsList ran with no box");
      return fetchFindingsPage(parseBboxParam(settled), filters, pageParam, signal);
    },
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor ?? null,
    enabled: settled !== null && !filters.empty,
    staleTime: FINDINGS_STALE_MS,
    placeholderData: keepPreviousData,
    retry: (failureCount, error) => failureCount < 1 && isTransient(error),
  });

  const items = query.data?.pages.flatMap((page) => page.items) ?? [];
  let status: FindingsListStatus;
  if (zoomedOut) status = "zoomed-out";
  else if (filters.empty) status = "filtered-out";
  else if (query.isError && isEndpointMissing(query.error)) status = "missing";
  else if (query.isError && items.length === 0) status = "error";
  else if (query.data === undefined) status = "loading";
  else status = "ready";

  return {
    status,
    items: status === "ready" || status === "error" ? items : [],
    hasMore: query.hasNextPage,
    loadingMore: query.isFetchingNextPage,
    stale: query.isPlaceholderData,
    error: query.error,
    loadMore: () => {
      if (query.hasNextPage && !query.isFetchingNextPage) void query.fetchNextPage();
    },
    retry: () => void query.refetch(),
  };
}
