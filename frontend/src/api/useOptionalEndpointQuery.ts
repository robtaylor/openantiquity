import { type QueryKey, type UseQueryOptions, type UseQueryResult, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { isEndpointMissing } from "./client.js";

export interface OptionalEndpointQuery<T> {
  query: UseQueryResult<T, Error>;
  /** True once the server has said it has no such endpoint. Nothing more is asked of it. */
  missing: boolean;
}

/**
 * A query against an endpoint the interface was built ahead of. Once the
 * server answers that it has no such endpoint (404, 405 or 501), this
 * component asks it nothing more for as long as it is mounted.
 */
export function useOptionalEndpointQuery<T, K extends QueryKey>(
  options: UseQueryOptions<T, Error, T, K> & { enabled?: boolean },
): OptionalEndpointQuery<T> {
  const [latched, setLatched] = useState(false);
  const query = useQuery({ ...options, enabled: (options.enabled ?? true) && !latched });
  const endpointMissing = query.isError && isEndpointMissing(query.error);
  useEffect(() => {
    if (endpointMissing) setLatched(true);
  }, [endpointMissing]);
  return { query, missing: latched || endpointMissing };
}
