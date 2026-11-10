import { type UseQueryResult, useQuery } from "@tanstack/react-query";
import { apiFetch, isTransient } from "./client.js";
import { type Meta, parseMeta } from "./meta.js";

export const META_QUERY_KEY = ["meta"] as const;

export const USE_FIXTURES = import.meta.env.VITE_USE_FIXTURES === "1";

export async function fetchMeta(signal?: AbortSignal): Promise<Meta> {
  if (USE_FIXTURES) {
    // Loaded on demand so the fixture stays out of a normal build.
    const { metaFixture } = await import("../test/fixtures/meta.js");
    return parseMeta(metaFixture);
  }
  return parseMeta(await apiFetch<unknown>("/meta", { signal }));
}

/** How long to wait before the one automatic second attempt. */
export const META_RETRY_DELAY_MS = 600;

/**
 * Vocabularies, tier definitions and the layer catalogue. Fetched once at
 * start-up and kept for the life of the page. A passing failure is retried
 * once before the person is told.
 */
export function useMeta(): UseQueryResult<Meta, Error> {
  return useQuery({
    queryKey: META_QUERY_KEY,
    queryFn: ({ signal }) => fetchMeta(signal),
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: Number.POSITIVE_INFINITY,
    retry: (failureCount, error) => failureCount < 1 && isTransient(error),
    retryDelay: META_RETRY_DELAY_MS,
  });
}
