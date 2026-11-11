import { type QueryClient, queryOptions, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { ApiError, isTransient } from "../../api/client.js";
import { fetchFinding } from "./api.js";
import { findingPageKeys } from "./keys.js";
import type { FindingDetail } from "./types.js";

/** A finding's page is asked for again when the person comes back to the tab, so a change made elsewhere shows. */
export function findingQuery(publicId: string) {
  return queryOptions({
    queryKey: findingPageKeys.detail(publicId),
    queryFn: ({ signal }) => fetchFinding(publicId, signal),
    refetchOnWindowFocus: true,
    retry: (failureCount, error) => failureCount < 1 && isTransient(error),
  });
}

/** True for the server's "no such finding": a wrong link, or one a moderator has hidden. */
export function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 404 || error.code === "finding_not_found");
}

export function useFinding(publicId: string) {
  return useQuery(findingQuery(publicId));
}

/** The map's markers and the Explore list ask again, because a change to one finding can move it. */
export function refreshFindingLists(client: QueryClient): void {
  for (const queryKey of findingPageKeys.lists) void client.invalidateQueries({ queryKey: [...queryKey] });
}

/**
 * Put the finding the server sent back after a change in place of the one
 * on the page, and have the map and the list ask again.
 */
export function useApplyFinding(): (finding: FindingDetail) => void {
  const client = useQueryClient();
  return useCallback(
    (finding: FindingDetail) => {
      client.setQueryData(findingPageKeys.detail(finding.public_id), finding);
      refreshFindingLists(client);
    },
    [client],
  );
}

/**
 * Change the finding on the page at once, ahead of the server, and get back
 * a function that puts it back as it was. For votes and following.
 */
export function useOptimisticFinding(publicId: string) {
  const client = useQueryClient();
  return useCallback(
    (change: (finding: FindingDetail) => FindingDetail): (() => void) => {
      const key = findingPageKeys.detail(publicId);
      const before = client.getQueryData<FindingDetail>(key);
      if (before) client.setQueryData(key, change(before));
      return () => {
        if (before) client.setQueryData(key, before);
      };
    },
    [client, publicId],
  );
}
