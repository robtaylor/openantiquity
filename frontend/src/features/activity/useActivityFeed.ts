import { keepPreviousData, useInfiniteQuery } from "@tanstack/react-query";
import { create } from "zustand";
import { isTransient } from "../../api/client.js";
import { useViewAreaStore } from "../../map/store.js";
import { useDebounced } from "../../ui/useDebounced.js";
import { bboxParam, snapBbox } from "../findings/api.js";
import { FINDINGS_DEBOUNCE_MS } from "../findings/useFindingsInBox.js";
import { type ActivityItem, fetchActivity } from "./api.js";
import { activityKeys } from "./keys.js";
import { type KindGroupId, kindsFor } from "./kinds.js";

export type FeedWhere = "everywhere" | "view";

interface FeedFiltersState {
  where: FeedWhere;
  /** The kinds of activity chosen, by group. None chosen shows every kind. */
  groups: KindGroupId[];
  setWhere: (where: FeedWhere) => void;
  setGroups: (groups: KindGroupId[]) => void;
  clear: () => void;
}

/**
 * The feed's filters, kept outside the panel so they survive the layer panel
 * opening over it.
 */
export const useFeedFilters = create<FeedFiltersState>()((set) => ({
  where: "everywhere",
  groups: [],
  setWhere: (where) => set({ where }),
  setGroups: (groups) => set({ groups }),
  clear: () => set({ where: "everywhere", groups: [] }),
}));

/** How long a page of the feed is used before it is asked for again, live events aside. */
export const FEED_STALE_MS = 30_000;

export type FeedStatus = "loading" | "error" | "ready";

export interface ActivityFeed {
  status: FeedStatus;
  items: ActivityItem[];
  hasMore: boolean;
  loadingMore: boolean;
  /** True while the items shown are for the filters or place before, and the new ones are on their way. */
  stale: boolean;
  error: Error | null;
  loadMore: () => void;
  retry: () => void;
}

/**
 * The feed, a page at a time, newest first. "In the map's view" asks for the
 * view widened by half a grid square, as the map's markers do, because the
 * server matches each event by the centre of its finding's square. The box
 * is taken once the map has held still.
 */
export function useActivityFeed(): ActivityFeed {
  const where = useFeedFilters((state) => state.where);
  const groups = useFeedFilters((state) => state.groups);
  const inView = where === "view";
  // Only "in the map's view" follows the map, so the feed doesn't redraw as it moves otherwise.
  const bounds = useViewAreaStore((state) => (inView ? state.bounds : null));
  const zoom = useViewAreaStore((state) => state.zoom);
  const box = useDebounced(bounds === null ? null : bboxParam(snapBbox(bounds, zoom)), FINDINGS_DEBOUNCE_MS);
  const bbox = inView ? box : null;
  const kinds = kindsFor(groups);

  const query = useInfiniteQuery({
    queryKey: activityKeys.feed(bbox, kinds),
    queryFn: ({ pageParam, signal }) => fetchActivity({ bbox, kinds }, pageParam, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor ?? null,
    // In view with no view yet, there is nothing to ask for.
    enabled: !inView || bbox !== null,
    staleTime: FEED_STALE_MS,
    placeholderData: keepPreviousData,
    retry: (failureCount, error) => failureCount < 1 && isTransient(error),
  });

  const items = query.data?.pages.flatMap((page) => page.items) ?? [];
  let status: FeedStatus;
  if (query.isError && items.length === 0) status = "error";
  else if (query.data === undefined) status = "loading";
  else status = "ready";

  return {
    status,
    items,
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
